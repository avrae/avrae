import pytest
import asyncio
from unittest.mock import MagicMock

from aliasing.constants import CVAR_SIZE_LIMIT, GVAR_SIZE_LIMIT, SVAR_SIZE_LIMIT, UVAR_SIZE_LIMIT
from cogsmisc.customization import (
    UTF8_MAX_BYTES_PER_CHAR,
    CVAR_FILE_SIZE_LIMIT,
    UVAR_FILE_SIZE_LIMIT,
    SVAR_FILE_SIZE_LIMIT,
    GVAR_FILE_SIZE_LIMIT,
    read_file_from_message,
    _get_value_or_file,
)
from cogs5e.models.errors import InvalidArgument


@pytest.fixture
def variable_limits():
    """Fixture providing variable size limits for parameterized testing"""
    return [
        (CVAR_SIZE_LIMIT, CVAR_FILE_SIZE_LIMIT, "CVAR"),
        (UVAR_SIZE_LIMIT, UVAR_FILE_SIZE_LIMIT, "UVAR"),
        (SVAR_SIZE_LIMIT, SVAR_FILE_SIZE_LIMIT, "SVAR"),
        (GVAR_SIZE_LIMIT, GVAR_FILE_SIZE_LIMIT, "GVAR"),
    ]


class MockAttachment:
    def __init__(self, content, size=None, filename="test.txt"):
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.size = size if size is not None else len(self.content)
        self.filename = filename

    async def read(self):
        return self.content


class MockContext:
    def __init__(self, attachments=None):
        self.message = MagicMock()
        self.message.attachments = attachments or []


class TestFileSizeLimits:
    def test_file_size_constants(self):
        """Test file size constants match variable limits"""
        assert CVAR_FILE_SIZE_LIMIT == UTF8_MAX_BYTES_PER_CHAR * CVAR_SIZE_LIMIT
        assert UVAR_FILE_SIZE_LIMIT == UTF8_MAX_BYTES_PER_CHAR * UVAR_SIZE_LIMIT
        assert SVAR_FILE_SIZE_LIMIT == UTF8_MAX_BYTES_PER_CHAR * SVAR_SIZE_LIMIT
        assert GVAR_FILE_SIZE_LIMIT == UTF8_MAX_BYTES_PER_CHAR * GVAR_SIZE_LIMIT


@pytest.mark.asyncio
class TestReadFileFromMessage:
    async def test_valid_utf8_file(self):
        """Test reading valid UTF-8 file content"""
        content = "test content 🎲"
        attachment = MockAttachment(content)
        ctx = MockContext([attachment])

        result = await read_file_from_message(ctx, 1000)
        assert result == content

    async def test_file_too_large(self):
        """Test file size limit enforcement"""
        content = "x" * 100
        attachment = MockAttachment(content)
        ctx = MockContext([attachment])

        with pytest.raises(InvalidArgument) as exc_info:
            await read_file_from_message(ctx, 50)

        assert str(exc_info.value) == "This file upload must not exceed 12 characters or 50 bytes."

    async def test_invalid_utf8_content(self):
        """Test handling of invalid UTF-8 content"""
        invalid_bytes = b"\x80\x81\x82\x83"
        attachment = MockAttachment(invalid_bytes)
        ctx = MockContext([attachment])

        with pytest.raises(InvalidArgument) as exc_info:
            await read_file_from_message(ctx, 1000)

        assert str(exc_info.value) == "Uploaded file must be text in utf-8 format"

    async def test_empty_file(self):
        """Test reading empty file"""
        attachment = MockAttachment("")
        ctx = MockContext([attachment])

        result = await read_file_from_message(ctx, 1000)
        assert result == ""

    async def test_no_attachments(self):
        """Test behavior when no attachments present"""
        ctx = MockContext([])

        with pytest.raises(IndexError):
            await read_file_from_message(ctx, 1000)

    async def test_unicode_content(self):
        """Test various Unicode characters"""
        content = "Hello 🌍 नमस्ते 🎭 こんにちは"
        attachment = MockAttachment(content)
        ctx = MockContext([attachment])

        result = await read_file_from_message(ctx, 1000)
        assert result == content

    async def test_size_limit_formatting(self):
        """Test error message formatting for size limits"""
        attachment = MockAttachment("x" * 10000)
        ctx = MockContext([attachment])

        with pytest.raises(InvalidArgument) as exc_info:
            await read_file_from_message(ctx, 5000)

        error_msg = str(exc_info.value)
        assert "This file upload must not exceed 1,250 characters or 5,000 bytes." == error_msg

    async def test_multiple_attachments_uses_first(self):
        """Test that when multiple files are attached, only the first is used"""
        attachment1 = MockAttachment("first file content")
        attachment2 = MockAttachment("second file content")
        ctx = MockContext([attachment1, attachment2])

        result = await read_file_from_message(ctx, 1000)
        assert result == "first file content"

    @pytest.mark.parametrize("offset,should_pass", [(-1, True), (0, True), (1, False)])
    async def test_exact_size_boundaries(self, offset, should_pass):
        """Test file size boundaries: under, at, and over limit"""
        size_limit = 100
        content = "x" * (size_limit + offset)
        attachment = MockAttachment(content)
        ctx = MockContext([attachment])

        if should_pass:
            result = await read_file_from_message(ctx, size_limit)
            assert result == content
        else:
            with pytest.raises(InvalidArgument) as exc_info:
                await read_file_from_message(ctx, size_limit)

            expected_chars = size_limit // UTF8_MAX_BYTES_PER_CHAR
            assert f"This file upload must not exceed {expected_chars:,} characters or {size_limit:,} bytes." == str(
                exc_info.value
            )

    async def test_concurrent_file_reads(self):
        """Test concurrent file reading operations"""
        contents = [f"content_{i}" for i in range(5)]
        attachments = [MockAttachment(content) for content in contents]
        contexts = [MockContext([att]) for att in attachments]

        # Run concurrent file reads
        tasks = [read_file_from_message(ctx, 1000) for ctx in contexts]
        results = await asyncio.gather(*tasks)

        # Verify all results are correct
        assert results == contents

    async def test_concurrent_file_reads_with_failures(self):
        """Test concurrent operations with some failures"""
        valid_attachment = MockAttachment("valid content")
        invalid_attachment = MockAttachment("x" * 200)  # Too large

        valid_ctx = MockContext([valid_attachment])
        invalid_ctx = MockContext([invalid_attachment])

        # Run concurrent operations
        valid_task = read_file_from_message(valid_ctx, 1000)
        invalid_task = read_file_from_message(invalid_ctx, 100)

        # Valid should succeed, invalid should fail
        result = await valid_task
        assert result == "valid content"

        with pytest.raises(InvalidArgument):
            await invalid_task


@pytest.mark.asyncio
class TestGetValueOrFile:
    async def test_value_provided_returns_value(self):
        """Test that provided value takes precedence over file"""
        attachment = MockAttachment("file content")
        ctx = MockContext([attachment])

        result = await _get_value_or_file(ctx, "direct value", 1000, allow_empty=False)
        assert result == "direct value"

    async def test_no_value_reads_file(self):
        """Test reading from file when no value provided"""
        file_content = "file content"
        attachment = MockAttachment(file_content)
        ctx = MockContext([attachment])

        result = await _get_value_or_file(ctx, None, 1000, allow_empty=False)
        assert result == file_content

    async def test_no_value_no_file_allow_empty_true(self):
        """Test behavior with no value, no file, allow_empty=True"""
        ctx = MockContext([])

        result = await _get_value_or_file(ctx, None, 1000, allow_empty=True)
        assert result is None

    async def test_no_value_no_file_allow_empty_false(self):
        """Test behavior with no value, no file, allow_empty=False"""
        ctx = MockContext([])

        with pytest.raises(InvalidArgument) as exc_info:
            await _get_value_or_file(ctx, None, 1000, allow_empty=False)

        assert str(exc_info.value) == "No input or file attachment found."

    async def test_file_size_limit_enforcement(self):
        """Test that file size limits are enforced in _get_value_or_file"""
        large_content = "x" * 200
        attachment = MockAttachment(large_content)
        ctx = MockContext([attachment])

        with pytest.raises(InvalidArgument) as exc_info:
            await _get_value_or_file(ctx, None, 100, allow_empty=False)

        assert str(exc_info.value) == "This file upload must not exceed 25 characters or 100 bytes."

    async def test_file_encoding_validation(self):
        """Test UTF-8 encoding validation in _get_value_or_file"""
        invalid_bytes = b"\xff\xfe\x00\x00"
        attachment = MockAttachment(invalid_bytes)
        ctx = MockContext([attachment])

        with pytest.raises(InvalidArgument) as exc_info:
            await _get_value_or_file(ctx, None, 1000, allow_empty=False)

        assert str(exc_info.value) == "Uploaded file must be text in utf-8 format"

    async def test_empty_file_allow_empty_true(self):
        """Test empty file with allow_empty=True"""
        attachment = MockAttachment("")
        ctx = MockContext([attachment])

        result = await _get_value_or_file(ctx, None, 1000, allow_empty=True)
        assert result == ""

    async def test_empty_file_allow_empty_false(self):
        """Test empty file with allow_empty=False"""
        attachment = MockAttachment("")
        ctx = MockContext([attachment])

        result = await _get_value_or_file(ctx, None, 1000, allow_empty=False)
        assert result == ""


@pytest.mark.asyncio
class TestVariableSizeScenarios:
    """Test realistic scenarios with actual variable size limits"""

    async def test_variable_at_exact_limit(self, variable_limits):
        """Test variable types at exact character limit"""
        for char_limit, file_limit, var_type in variable_limits:
            content = "x" * char_limit
            attachment = MockAttachment(content)
            ctx = MockContext([attachment])

            result = await read_file_from_message(ctx, file_limit)
            assert result == content
            assert len(result) == char_limit

    async def test_variable_over_file_limit(self, variable_limits):
        """Test variable types over file byte limit"""
        for char_limit, file_limit, var_type in variable_limits:
            content = "x" * (file_limit + 1)
            attachment = MockAttachment(content)
            ctx = MockContext([attachment])

            with pytest.raises(InvalidArgument) as exc_info:
                await read_file_from_message(ctx, file_limit)

            expected_chars = file_limit // UTF8_MAX_BYTES_PER_CHAR
            assert (
                str(exc_info.value)
                == f"This file upload must not exceed {expected_chars:,} characters or {file_limit:,} bytes."
            )

    async def test_variable_near_limit(self, variable_limits):
        """Test variable types with content near the character limit"""
        for char_limit, file_limit, var_type in variable_limits:
            content = "x" * max(1, char_limit - 100)  # Ensure at least 1 character
            attachment = MockAttachment(content)
            ctx = MockContext([attachment])

            result = await read_file_from_message(ctx, file_limit)
            assert result == content
            assert len(result) == max(1, char_limit - 100)

    async def test_multibyte_unicode_size_calculation(self):
        """Test that multibyte unicode characters are handled correctly"""
        # Use 4-byte unicode character
        four_byte_char = "𝕏"
        content = four_byte_char * 10  # 40 bytes total
        attachment = MockAttachment(content)
        ctx = MockContext([attachment])

        # Should work with limit >= 40 bytes
        result = await read_file_from_message(ctx, 50)
        assert result == content

        # Should fail with limit < 40 bytes
        with pytest.raises(InvalidArgument):
            await read_file_from_message(ctx, 30)


@pytest.mark.asyncio
class TestEdgeCases:
    @pytest.mark.parametrize(
        "content,description",
        [
            ("", "empty content"),
            ("   \n\t   \n   ", "whitespace only content"),
            ("line1\nline2\r\nline3\n", "content with preserved newlines"),
            ('{"key": "value", "number": 42, "array": [1, 2, 3]}', "JSON-like content"),
            ("def spell_attack(damage, spell_level):\n    return damage + spell_level", "code-like content"),
            ("Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?`~", "content with special characters"),
            ("Hello 🌍 नमस्ते 🎭 こんにちは", "unicode content from different scripts"),
        ],
    )
    async def test_various_content_types(self, content, description):
        """Test reading files with various content types"""
        attachment = MockAttachment(content)
        ctx = MockContext([attachment])

        result = await read_file_from_message(ctx, 1000)
        assert result == content

    async def test_newlines_count_preserved(self):
        """Test that specific newline count is preserved"""
        content = "line1\nline2\r\nline3\n"
        attachment = MockAttachment(content)
        ctx = MockContext([attachment])

        result = await read_file_from_message(ctx, 1000)
        assert result == content
        assert result.count("\n") == 3
