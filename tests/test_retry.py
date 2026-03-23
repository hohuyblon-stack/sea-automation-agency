"""
Tests for utils/retry.py — Retry with exponential backoff.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.retry import retry_call, retry_with_backoff


class TestRetryWithBackoff:
    @patch("utils.retry.time.sleep")
    def test_succeeds_first_try(self, mock_sleep):
        @retry_with_backoff(max_retries=3)
        def success():
            return "ok"

        assert success() == "ok"
        mock_sleep.assert_not_called()

    @patch("utils.retry.time.sleep")
    def test_retries_on_failure(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01, retryable_exceptions=(ValueError,))
        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = eventually_succeeds()
        assert result == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("utils.retry.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        @retry_with_backoff(max_retries=2, base_delay=0.01, retryable_exceptions=(ValueError,))
        def always_fails():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            always_fails()
        assert mock_sleep.call_count == 2

    @patch("utils.retry.time.sleep")
    def test_non_retryable_exception_raises_immediately(self, mock_sleep):
        @retry_with_backoff(max_retries=3, retryable_exceptions=(ValueError,))
        def type_error():
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            type_error()
        mock_sleep.assert_not_called()

    @patch("utils.retry.time.sleep")
    def test_exponential_delay(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=1.0, jitter=False, retryable_exceptions=(ValueError,))
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("fail")
            return "ok"

        fails_twice()
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert delays[0] == 1.0   # base_delay * 2^0
        assert delays[1] == 2.0   # base_delay * 2^1

    @patch("utils.retry.time.sleep")
    def test_max_delay_cap(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=5, base_delay=10.0, max_delay=15.0, jitter=False, retryable_exceptions=(ValueError,))
        def fails_many():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                raise ValueError("fail")
            return "ok"

        fails_many()
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert all(d <= 15.0 for d in delays)

    @patch("utils.retry.time.sleep")
    def test_preserves_function_name(self, mock_sleep):
        @retry_with_backoff(max_retries=1)
        def my_function():
            return True

        assert my_function.__name__ == "my_function"


class TestRetryCall:
    @patch("utils.retry.time.sleep")
    def test_basic_call(self, mock_sleep):
        func = MagicMock(return_value="result")
        result = retry_call(func, max_retries=3)
        assert result == "result"
        func.assert_called_once()

    @patch("utils.retry.time.sleep")
    def test_with_args_and_kwargs(self, mock_sleep):
        func = MagicMock(return_value="ok")
        retry_call(func, args=(1, 2), kwargs={"key": "val"}, max_retries=1)
        func.assert_called_with(1, 2, key="val")

    @patch("utils.retry.time.sleep")
    def test_retries_on_exception(self, mock_sleep):
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            return "ok"

        result = retry_call(flaky, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 2
