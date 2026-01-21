"""Tests for directive mental model functionality.

Mental models now only support the 'directive' subtype - hard rules injected into prompts.
Other types of consolidated knowledge are handled by Learnings and Pinned Reflections.
"""

import uuid

import pytest

from hindsight_api.engine.memory_engine import MemoryEngine


@pytest.fixture
async def memory_with_bank(memory: MemoryEngine, request_context):
    """Memory engine with a bank that has some data.

    Uses a unique bank_id to avoid conflicts between parallel tests.
    """
    # Use unique bank_id to avoid conflicts between parallel tests
    bank_id = f"test-directives-{uuid.uuid4().hex[:8]}"

    # Ensure bank exists
    await memory.get_bank_profile(bank_id, request_context=request_context)

    # Add some test data
    await memory.retain_batch_async(
        bank_id=bank_id,
        contents=[
            {"content": "The team has daily standups at 9am where everyone shares their progress."},
            {"content": "Alice is the frontend engineer and specializes in React."},
            {"content": "Bob is the backend engineer and owns the API services."},
        ],
        request_context=request_context,
    )

    # Wait for any background tasks from retain to complete
    await memory.wait_for_background_tasks()

    yield memory, bank_id

    # Cleanup
    await memory.delete_bank(bank_id, request_context=request_context)


class TestBankMission:
    """Test bank mission operations."""

    async def test_set_and_get_mission(self, memory: MemoryEngine, request_context):
        """Test setting and getting a bank's mission."""
        bank_id = f"test-mission-{uuid.uuid4().hex[:8]}"

        # Set mission
        result = await memory.set_bank_mission(
            bank_id=bank_id,
            mission="Track customer feedback",
            request_context=request_context,
        )

        assert result["bank_id"] == bank_id
        assert result["mission"] == "Track customer feedback"

        # Get mission via profile
        profile = await memory.get_bank_profile(bank_id=bank_id, request_context=request_context)
        assert profile["mission"] == "Track customer feedback"

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)


class TestDirectives:
    """Test directive mental model functionality."""

    async def test_create_directive(self, memory: MemoryEngine, request_context):
        """Test creating a directive mental model with user-provided observations."""
        bank_id = f"test-directive-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Create a directive with observations
        model = await memory.create_mental_model(
            bank_id=bank_id,
            name="Competitor Policy",
            description="Rules about mentioning competitors",
            subtype="directive",
            observations=[
                {"title": "Never mention", "content": "Never mention competitor product names directly"},
                {"title": "Redirect", "content": "If asked about competitors, redirect to our features"},
            ],
            request_context=request_context,
        )

        assert model["name"] == "Competitor Policy"
        assert model["description"] == "Rules about mentioning competitors"
        assert model["subtype"] == "directive"
        assert len(model["observations"]) == 2
        assert model["observations"][0].title == "Never mention"
        assert model["observations"][0].content == "Never mention competitor product names directly"

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)

    async def test_directive_crud(self, memory: MemoryEngine, request_context):
        """Test basic CRUD operations for directives."""
        bank_id = f"test-directive-crud-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Create
        model = await memory.create_mental_model(
            bank_id=bank_id,
            name="Test Directive",
            description="A test directive",
            subtype="directive",
            observations=[{"title": "Rule 1", "content": "Follow this rule"}],
            request_context=request_context,
        )
        assert model["id"] == "directive-test-directive"

        # Read
        retrieved = await memory.get_mental_model(
            bank_id=bank_id,
            model_id=model["id"],
            request_context=request_context,
        )
        assert retrieved is not None
        assert retrieved["name"] == "Test Directive"
        assert retrieved["subtype"] == "directive"

        # List
        models = await memory.list_mental_models(
            bank_id=bank_id,
            request_context=request_context,
        )
        assert len(models) == 1
        assert models[0]["id"] == model["id"]

        # List with subtype filter
        directives = await memory.list_mental_models(
            bank_id=bank_id,
            subtype="directive",
            request_context=request_context,
        )
        assert len(directives) == 1

        # Delete
        deleted = await memory.delete_mental_model(
            bank_id=bank_id,
            model_id=model["id"],
            request_context=request_context,
        )
        assert deleted is True

        # Verify deletion
        retrieved_after = await memory.get_mental_model(
            bank_id=bank_id,
            model_id=model["id"],
            request_context=request_context,
        )
        assert retrieved_after is None

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)

    async def test_directive_get_includes_observations(self, memory: MemoryEngine, request_context):
        """Test that getting a directive returns its user-provided observations."""
        bank_id = f"test-directive-get-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Create a directive with observations
        created = await memory.create_mental_model(
            bank_id=bank_id,
            name="Meeting Rules",
            description="Rules for scheduling meetings",
            subtype="directive",
            observations=[
                {"title": "No mornings", "content": "Never schedule meetings before noon"},
                {"title": "Max duration", "content": "Meetings should be 30 minutes max"},
            ],
            request_context=request_context,
        )

        # Get the directive
        retrieved = await memory.get_mental_model(
            bank_id=bank_id,
            model_id=created["id"],
            request_context=request_context,
        )

        assert retrieved is not None
        assert retrieved["subtype"] == "directive"
        assert len(retrieved["observations"]) == 2
        assert retrieved["observations"][0].title == "No mornings"
        assert retrieved["observations"][1].title == "Max duration"

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)

    async def test_directive_requires_observations(self, memory: MemoryEngine, request_context):
        """Test that creating a directive without observations fails."""
        bank_id = f"test-directive-no-obs-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Try to create directive without observations
        with pytest.raises(ValueError) as exc_info:
            await memory.create_mental_model(
                bank_id=bank_id,
                name="Bad Directive",
                description="A directive without observations",
                subtype="directive",
                # No observations provided
                request_context=request_context,
            )

        assert "observations" in str(exc_info.value).lower()

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)

    async def test_create_duplicate_directive_fails(self, memory: MemoryEngine, request_context):
        """Test that creating a duplicate directive fails."""
        bank_id = f"test-directive-dup-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Create first directive
        await memory.create_mental_model(
            bank_id=bank_id,
            name="Test Rule",
            description="First directive",
            subtype="directive",
            observations=[{"title": "Rule", "content": "Follow this"}],
            request_context=request_context,
        )

        # Try to create duplicate
        with pytest.raises(ValueError) as exc_info:
            await memory.create_mental_model(
                bank_id=bank_id,
                name="Test Rule",
                description="Second directive",
                subtype="directive",
                observations=[{"title": "Rule 2", "content": "Follow this too"}],
                request_context=request_context,
            )

        assert "already exists" in str(exc_info.value).lower()

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)

    async def test_only_directive_subtype_supported(self, memory: MemoryEngine, request_context):
        """Test that only directive subtype is supported."""
        bank_id = f"test-unsupported-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Try to create with pinned subtype (no longer supported)
        with pytest.raises(ValueError) as exc_info:
            await memory.create_mental_model(
                bank_id=bank_id,
                name="Pinned Model",
                description="Should fail",
                subtype="pinned",
                request_context=request_context,
            )

        assert "unsupported" in str(exc_info.value).lower() or "only" in str(exc_info.value).lower()

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)


class TestDirectiveTags:
    """Test tags functionality for directives."""

    async def test_directive_with_tags(self, memory: MemoryEngine, request_context):
        """Test creating a directive with tags."""
        bank_id = f"test-directive-tags-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Create a directive with tags
        model = await memory.create_mental_model(
            bank_id=bank_id,
            name="Tagged Rule",
            description="A rule with tags",
            subtype="directive",
            observations=[{"title": "Rule", "content": "Follow this rule"}],
            tags=["project-a", "team-x"],
            request_context=request_context,
        )

        assert model["tags"] == ["project-a", "team-x"]

        # Retrieve and verify tags
        retrieved = await memory.get_mental_model(
            bank_id=bank_id,
            model_id=model["id"],
            request_context=request_context,
        )
        assert retrieved["tags"] == ["project-a", "team-x"]

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)

    async def test_list_directives_by_tags(self, memory: MemoryEngine, request_context):
        """Test listing directives filtered by tags."""
        bank_id = f"test-directive-tags-list-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Create directives with different tags
        await memory.create_mental_model(
            bank_id=bank_id,
            name="Rule A",
            description="Rule for project A",
            subtype="directive",
            observations=[{"title": "Rule", "content": "Follow this"}],
            tags=["project-a"],
            request_context=request_context,
        )

        await memory.create_mental_model(
            bank_id=bank_id,
            name="Rule B",
            description="Rule for project B",
            subtype="directive",
            observations=[{"title": "Rule", "content": "Follow this"}],
            tags=["project-b"],
            request_context=request_context,
        )

        # List all
        all_models = await memory.list_mental_models(
            bank_id=bank_id,
            request_context=request_context,
        )
        assert len(all_models) == 2

        # Filter by project-a tag
        filtered = await memory.list_mental_models(
            bank_id=bank_id,
            tags=["project-a"],
            tags_match="any_strict",
            request_context=request_context,
        )
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Rule A"

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)


class TestReflect:
    """Test reflect endpoint."""

    async def test_reflect_basic(self, memory_with_bank, request_context):
        """Test basic reflect query works."""
        memory, bank_id = memory_with_bank

        # Run a reflect query
        result = await memory.reflect_async(
            bank_id=bank_id,
            query="Who are the team members?",
            request_context=request_context,
        )

        assert result.text is not None
        assert len(result.text) > 0


class TestDirectivesInReflect:
    """Test that directives are followed during reflect operations."""

    async def test_reflect_follows_language_directive(self, memory: MemoryEngine, request_context):
        """Test that reflect follows a directive to respond in a specific language."""
        bank_id = f"test-directive-reflect-{uuid.uuid4().hex[:8]}"

        # Ensure bank exists
        await memory.get_bank_profile(bank_id, request_context=request_context)

        # Add some content in English
        await memory.retain_batch_async(
            bank_id=bank_id,
            contents=[
                {"content": "Alice is a software engineer who works at Google."},
                {"content": "Alice enjoys hiking on weekends and has been to Yosemite."},
                {"content": "Alice is currently working on a machine learning project."},
            ],
            request_context=request_context,
        )
        await memory.wait_for_background_tasks()

        # Create a directive to always respond in French
        await memory.create_mental_model(
            bank_id=bank_id,
            name="Language Policy",
            description="Rules about language usage",
            subtype="directive",
            observations=[
                {
                    "title": "French Only",
                    "content": "ALWAYS respond in French language. Never respond in English.",
                },
            ],
            request_context=request_context,
        )

        # Run reflect query
        result = await memory.reflect_async(
            bank_id=bank_id,
            query="What does Alice do for work?",
            request_context=request_context,
        )

        assert result.text is not None
        assert len(result.text) > 0

        # Check that the response contains French words/patterns
        # Common French words that would appear when talking about someone's job
        french_indicators = [
            "elle",
            "travaille",
            "est",
            "une",
            "le",
            "la",
            "qui",
            "chez",
            "logiciel",
            "ingénieur",
            "ingénieure",
            "développeur",
            "développeuse",
        ]
        response_lower = result.text.lower()

        # At least some French words should appear in the response
        french_word_count = sum(1 for word in french_indicators if word in response_lower)
        assert (
            french_word_count >= 2
        ), f"Expected French response, but got: {result.text[:200]}"

        # Cleanup
        await memory.delete_bank(bank_id, request_context=request_context)


class TestDirectivesPromptInjection:
    """Test that directives are properly injected into the system prompt."""

    def test_build_directives_section_empty(self):
        """Test that empty directives returns empty string."""
        from hindsight_api.engine.reflect.prompts import build_directives_section

        result = build_directives_section([])
        assert result == ""

    def test_build_directives_section_with_observations(self):
        """Test that directives with observations are formatted correctly."""
        from hindsight_api.engine.reflect.prompts import build_directives_section

        directives = [
            {
                "name": "Competitor Policy",
                "observations": [
                    {"title": "Never mention", "content": "Never mention competitor names"},
                    {"title": "Redirect", "content": "Redirect to our features"},
                ],
            }
        ]

        result = build_directives_section(directives)

        assert "## DIRECTIVES (MANDATORY)" in result
        assert "**Never mention**: Never mention competitor names" in result
        assert "**Redirect**: Redirect to our features" in result
        assert "NEVER violate these directives" in result

    def test_build_directives_section_fallback_to_description(self):
        """Test that directives without observations fall back to description."""
        from hindsight_api.engine.reflect.prompts import build_directives_section

        directives = [
            {
                "name": "Simple Rule",
                "description": "Just a simple rule description",
                "observations": [],
            }
        ]

        result = build_directives_section(directives)

        assert "**Simple Rule**: Just a simple rule description" in result

    def test_system_prompt_includes_directives(self):
        """Test that build_system_prompt_for_tools includes directives."""
        from hindsight_api.engine.reflect.prompts import build_system_prompt_for_tools

        bank_profile = {"name": "Test Bank", "mission": "Test mission"}
        directives = [
            {
                "name": "Test Directive",
                "observations": [{"title": "Rule", "content": "Follow this rule"}],
            }
        ]

        prompt = build_system_prompt_for_tools(
            bank_profile=bank_profile,
            directives=directives,
        )

        assert "## DIRECTIVES (MANDATORY)" in prompt
        assert "**Rule**: Follow this rule" in prompt
        # Directives should appear before CRITICAL RULES
        directives_pos = prompt.find("## DIRECTIVES")
        critical_rules_pos = prompt.find("## CRITICAL RULES")
        assert directives_pos < critical_rules_pos
