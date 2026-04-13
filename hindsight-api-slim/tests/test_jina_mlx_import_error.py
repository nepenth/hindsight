"""
Regression test for the JinaMLXCrossEncoder import-error handling.

See: https://github.com/vectorize-io/hindsight/issues/994

Before the fix, the bare `except ImportError` around `import mlx_lm` masked
*any* ImportError raised transitively during mlx_lm's own initialization
(e.g. transformers 5.x's _LazyModule race producing
`ImportError: cannot import name 'AutoTokenizer' from 'transformers'`),
replacing it with a misleading "install mlx" message.

These tests verify:
1. A transitive ImportError raised from inside mlx_lm surfaces verbatim.
2. A genuine "package not installed" ImportError still produces the install hint.
"""

import sys
from unittest.mock import patch

import pytest

from hindsight_api.engine.cross_encoder import JinaMLXCrossEncoder


@pytest.mark.asyncio
async def test_initialize_surfaces_transitive_import_error():
    """A transformers-lazy-load-style failure must propagate, not be masked."""
    encoder = JinaMLXCrossEncoder()

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "mlx_lm":
            raise ImportError("cannot import name 'AutoTokenizer' from 'transformers'")
        return real_import(name, *args, **kwargs)

    # Ensure mlx_lm isn't already cached from an earlier import
    sys.modules.pop("mlx_lm", None)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="AutoTokenizer"):
            await encoder.initialize()


@pytest.mark.asyncio
async def test_initialize_reports_install_hint_when_mlx_missing():
    """A genuine 'package not installed' error still gets the friendly install hint."""
    encoder = JinaMLXCrossEncoder()

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "mlx_lm" or name.startswith("mlx_lm."):
            raise ImportError("No module named 'mlx_lm'")
        if name == "mlx" or name.startswith("mlx."):
            raise ImportError("No module named 'mlx'")
        return real_import(name, *args, **kwargs)

    sys.modules.pop("mlx_lm", None)
    sys.modules.pop("mlx", None)
    sys.modules.pop("mlx.core", None)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="mlx and mlx-lm are required"):
            await encoder.initialize()
