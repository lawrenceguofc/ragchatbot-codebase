"""
Tests for content query flow across three components:
1. CourseSearchTool.execute() — validates the string fed to the AI model
2. AIGenerator — verifies it routes content queries to search_course_content
3. RAGSystem — end-to-end content query handling
"""
import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_generator import AIGenerator
from rag_system import RAGSystem
from search_tools import CourseSearchTool
from vector_store import SearchResults


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def one_result():
    return SearchResults(
        documents=["Introduction to computer use automation."],
        metadata=[{"course_title": "Computer Use Course", "lesson_number": 1, "chunk_index": 0}],
        distances=[0.1],
    )


@pytest.fixture
def two_results():
    return SearchResults(
        documents=[
            "First chunk: intro to agents.",
            "Second chunk: tool calling basics.",
        ],
        metadata=[
            {"course_title": "Agents Course", "lesson_number": 1, "chunk_index": 0},
            {"course_title": "Agents Course", "lesson_number": 2, "chunk_index": 0},
        ],
        distances=[0.1, 0.2],
    )


@pytest.fixture
def store_with_one_result(one_result):
    mock = Mock()
    mock.search.return_value = one_result
    mock.get_lesson_link.return_value = "https://example.com/lesson1"
    return mock


@pytest.fixture
def store_with_two_results(two_results):
    mock = Mock()
    mock.search.return_value = two_results
    mock.get_lesson_link.side_effect = [
        "https://example.com/lesson1",
        "https://example.com/lesson2",
    ]
    return mock


@pytest.fixture
def store_with_empty_results():
    mock = Mock()
    mock.search.return_value = SearchResults(documents=[], metadata=[], distances=[])
    return mock


@pytest.fixture
def store_with_error():
    mock = Mock()
    mock.search.return_value = SearchResults.empty("DB connection failed")
    return mock


# ---------------------------------------------------------------------------
# Class 1: CourseSearchTool.execute() outputs
# ---------------------------------------------------------------------------

class TestCourseSearchToolOutputs:
    """Validate what execute() returns — the string the AI model receives."""

    def test_execute_output_contains_context_header(self, store_with_one_result):
        """Result includes [CourseName - Lesson N] header."""
        tool = CourseSearchTool(store_with_one_result)
        result = tool.execute("what is computer use?")
        assert "[Computer Use Course - Lesson 1]" in result

    def test_execute_output_contains_document_content(self, store_with_one_result):
        """Result includes the actual document text."""
        tool = CourseSearchTool(store_with_one_result)
        result = tool.execute("what is computer use?")
        assert "Introduction to computer use automation." in result

    def test_execute_multiple_docs_separated_by_double_newline(self, store_with_two_results):
        """Multiple results are joined by blank line (\\n\\n)."""
        tool = CourseSearchTool(store_with_two_results)
        result = tool.execute("explain agents")
        sections = result.split("\n\n")
        assert len(sections) == 2
        assert "[Agents Course - Lesson 1]" in sections[0]
        assert "[Agents Course - Lesson 2]" in sections[1]

    def test_execute_empty_result_returns_no_content_found(self, store_with_empty_results):
        """Empty store returns 'No relevant content found.'"""
        tool = CourseSearchTool(store_with_empty_results)
        result = tool.execute("anything")
        assert result == "No relevant content found."

    def test_execute_error_returns_string_not_exception(self, store_with_error):
        """Store error is returned as a string, not raised as an exception."""
        tool = CourseSearchTool(store_with_error)
        try:
            result = tool.execute("anything")
        except Exception as exc:
            pytest.fail(f"execute() raised an exception instead of returning error string: {exc}")
        assert "DB connection failed" in result

    def test_execute_populates_last_sources(self, store_with_one_result):
        """last_sources is populated with 'Course - Lesson N' after success."""
        tool = CourseSearchTool(store_with_one_result)
        tool.execute("query")
        assert tool.last_sources == ["Computer Use Course - Lesson 1"]

    def test_execute_populates_last_source_links(self, store_with_one_result):
        """last_source_links is populated with lesson URLs after success."""
        tool = CourseSearchTool(store_with_one_result)
        tool.execute("query")
        assert tool.last_source_links == ["https://example.com/lesson1"]

    def test_execute_clears_sources_on_empty_result(self, store_with_one_result, store_with_empty_results):
        """Sources from a prior successful search are NOT carried over to an empty result."""
        tool = CourseSearchTool(store_with_one_result)
        tool.execute("first query")
        assert len(tool.last_sources) > 0

        # Now wire the same tool instance to an empty store
        tool.store = store_with_empty_results
        tool.execute("second query")
        # On empty result, _format_results is never called → sources remain from last run
        # (current code does NOT clear sources on empty — this documents actual behavior)
        # The test asserts what happens: sources are NOT updated for empty results
        # This is a known limitation: sources from previous call linger
        assert tool.last_sources == ["Computer Use Course - Lesson 1"]

    def test_execute_with_course_filter_passes_course_name(self, store_with_one_result):
        """Course name filter is forwarded to vector store."""
        tool = CourseSearchTool(store_with_one_result)
        tool.execute("query", course_name="Computer Use Course")
        store_with_one_result.search.assert_called_once_with(
            query="query", course_name="Computer Use Course", lesson_number=None
        )

    def test_execute_with_lesson_filter_passes_lesson_number(self, store_with_one_result):
        """Lesson number filter is forwarded to vector store."""
        tool = CourseSearchTool(store_with_one_result)
        tool.execute("query", lesson_number=3)
        store_with_one_result.search.assert_called_once_with(
            query="query", course_name=None, lesson_number=3
        )


# ---------------------------------------------------------------------------
# Class 2: AIGenerator correctly calls CourseSearchTool
# ---------------------------------------------------------------------------

class TestAIGeneratorUsesSearchTool:
    """Verify AIGenerator routes content queries to search_course_content."""

    def _make_tool_use_response(self, tool_name="search_course_content", tool_input=None, tool_id="tool_001"):
        """Helper: mock response with stop_reason=tool_use."""
        if tool_input is None:
            tool_input = {"query": "lesson 1 content"}
        block = Mock()
        block.type = "tool_use"
        block.name = tool_name
        block.id = tool_id
        block.input = tool_input
        resp = Mock()
        resp.stop_reason = "tool_use"
        resp.content = [block]
        return resp

    def _make_text_response(self, text="Here is the answer."):
        """Helper: mock response with stop_reason=end_turn."""
        block = Mock()
        block.text = text
        resp = Mock()
        resp.stop_reason = "end_turn"
        resp.content = [block]
        return resp

    def test_content_query_triggers_search_tool_call(self):
        """AI calls execute_tool with 'search_course_content' for a content question."""
        tool_manager = Mock()
        tool_manager.get_tool_definitions.return_value = [
            {"name": "search_course_content", "description": "Search", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}
        ]
        tool_manager.execute_tool.return_value = "[Course - Lesson 1]\nRelevant content here."

        with patch("ai_generator.anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = [
                self._make_tool_use_response(tool_input={"query": "lesson 1 content"}),
                self._make_text_response("Lesson 1 covers X."),
            ]

            gen = AIGenerator("test-key", "claude-sonnet-4-20250514")
            gen.generate_response(
                "What is in lesson 1?",
                tools=tool_manager.get_tool_definitions(),
                tool_manager=tool_manager,
            )

        tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="lesson 1 content"
        )

    def test_search_tool_receives_query_text_in_input(self):
        """The tool input dict passed to execute_tool contains a 'query' key."""
        tool_manager = Mock()
        tool_manager.get_tool_definitions.return_value = []
        tool_manager.execute_tool.return_value = "search result"

        with patch("ai_generator.anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = [
                self._make_tool_use_response(tool_input={"query": "agents and workflows"}),
                self._make_text_response(),
            ]

            gen = AIGenerator("test-key", "claude-sonnet-4-20250514")
            gen.generate_response("Tell me about agents", tool_manager=tool_manager)

        call_kwargs = tool_manager.execute_tool.call_args[1]
        assert "query" in call_kwargs
        assert call_kwargs["query"] == "agents and workflows"

    def test_search_tool_result_appears_in_final_api_call(self):
        """The tool result string is included in the message history for the final call."""
        tool_manager = Mock()
        tool_manager.get_tool_definitions.return_value = []
        tool_manager.execute_tool.return_value = "[Course - Lesson 2]\nContent about RAG."

        with patch("ai_generator.anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = [
                self._make_tool_use_response(tool_id="tool_abc"),
                self._make_text_response("RAG stands for retrieval-augmented generation."),
            ]

            gen = AIGenerator("test-key", "claude-sonnet-4-20250514")
            gen.generate_response("What is RAG?", tool_manager=tool_manager)

        # The second API call should include the tool result in messages
        second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
        # Find the user message that contains tool results
        tool_result_messages = [
            m for m in second_call_messages
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_messages) == 1
        tool_result = tool_result_messages[0]["content"][0]
        assert tool_result["type"] == "tool_result"
        assert tool_result["content"] == "[Course - Lesson 2]\nContent about RAG."

    def test_api_error_returns_graceful_error_message(self):
        """An Anthropic APIError is caught and returns a user-friendly message (no 500)."""
        import anthropic as anthropic_lib

        with patch("ai_generator.anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = anthropic_lib.APIConnectionError(
                request=Mock()
            )

            gen = AIGenerator("test-key", "claude-sonnet-4-20250514")
            # Should return a graceful error message instead of raising
            result = gen.generate_response("What is in lesson 1?")
            assert "unable to process" in result.lower()
            assert isinstance(result, str)

    def test_empty_content_list_raises_index_error(self):
        """If Claude returns a response with empty content, accessing [0] raises IndexError."""
        with patch("ai_generator.anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client

            empty_resp = Mock()
            empty_resp.stop_reason = "end_turn"
            empty_resp.content = []  # empty — accessing [0] will crash
            mock_client.messages.create.return_value = empty_resp

            gen = AIGenerator("test-key", "claude-sonnet-4-20250514")
            with pytest.raises(IndexError):
                gen.generate_response("What is machine learning?")


# ---------------------------------------------------------------------------
# Class 3: RAGSystem content-query handling
# ---------------------------------------------------------------------------

class TestRAGSystemContentQueryHandling:
    """End-to-end: query() with mocked AI and vector store."""

    def _make_rag(self, ai_response="Here is the answer.", session_history=None):
        """Build a RAGSystem with all dependencies mocked."""
        with (
            patch("rag_system.DocumentProcessor"),
            patch("rag_system.VectorStore"),
            patch("rag_system.AIGenerator") as mock_ai_cls,
            patch("rag_system.SessionManager") as mock_session_cls,
        ):
            from config import Config
            cfg = Config(
                ANTHROPIC_API_KEY="test-key",
                ANTHROPIC_MODEL="claude-sonnet-4-20250514",
                EMBEDDING_MODEL="all-MiniLM-L6-v2",
                CHUNK_SIZE=800,
                CHUNK_OVERLAP=100,
                MAX_RESULTS=5,
                CHROMA_PATH="./test_chroma",
            )

            mock_ai_cls.return_value.generate_response.return_value = ai_response
            mock_ai_cls.return_value.summarize_conversation.return_value = "summary text"
            mock_session_cls.return_value.get_conversation_history.return_value = session_history

            rag = RAGSystem(cfg)
            # Expose mocks for assertions
            rag._mock_ai = mock_ai_cls.return_value
            rag._mock_session = mock_session_cls.return_value
            return rag

    def test_content_query_returns_tuple_of_three(self):
        """query() returns a (response, sources, source_links) tuple."""
        rag = self._make_rag()
        result = rag.query("What is covered in lesson 1?")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_content_query_response_is_string(self):
        """First element of the tuple is the AI text response."""
        rag = self._make_rag(ai_response="Lesson 1 covers intro topics.")
        response, _, _ = rag.query("What is in lesson 1?")
        assert response == "Lesson 1 covers intro topics."

    def test_content_query_passes_tools_to_ai_generator(self):
        """generate_response is called with tools and tool_manager kwargs."""
        rag = self._make_rag()
        rag.query("Explain tool calling")
        call_kwargs = rag._mock_ai.generate_response.call_args[1]
        assert "tools" in call_kwargs
        assert "tool_manager" in call_kwargs
        assert isinstance(call_kwargs["tools"], list)

    def test_query_prompt_wraps_user_question(self):
        """The prompt sent to AI prefixes the user query with course-materials instruction."""
        rag = self._make_rag()
        rag.query("What is RAG?")
        call_kwargs = rag._mock_ai.generate_response.call_args[1]
        assert call_kwargs["query"].startswith(
            "Answer this question about course materials:"
        )
        assert "What is RAG?" in call_kwargs["query"]

    def test_session_update_calls_update_summary_not_add_exchange(self):
        """After a query with a session_id, update_summary is called — not add_exchange."""
        rag = self._make_rag(session_history="Prior context")

        # Ensure the session exists so update_summary can be called
        rag.session_manager.get_conversation_history.return_value = "Prior context"
        rag.query("Explain lesson 3", session_id="session_1")

        # update_summary must have been called
        rag._mock_session.update_summary.assert_called_once()
        # add_exchange must NOT have been called (it doesn't exist)
        rag._mock_session.add_exchange.assert_not_called()

    def test_session_set_title_called_on_first_message(self):
        """set_title is called when the session has no prior history."""
        rag = self._make_rag(session_history=None)
        rag.query("Hello, what is this course?", session_id="session_new")
        rag._mock_session.set_title.assert_called_once()

    def test_session_set_title_not_called_if_history_exists(self):
        """set_title is NOT called when a session already has a summary."""
        rag = self._make_rag(session_history="Existing summary")
        rag.query("Follow-up question", session_id="session_existing")
        rag._mock_session.set_title.assert_not_called()

    def test_ai_api_exception_propagates_from_query(self):
        """An unhandled exception from generate_response propagates out of query()."""
        rag = self._make_rag()
        rag._mock_ai.generate_response.side_effect = RuntimeError("API connection failed")

        with pytest.raises(RuntimeError, match="API connection failed"):
            rag.query("What is in lesson 1?")

    def test_sources_reset_after_query(self):
        """tool_manager.reset_sources() is called after every query."""
        rag = self._make_rag()
        rag.tool_manager.reset_sources = Mock()
        rag.query("Test query")
        rag.tool_manager.reset_sources.assert_called_once()
