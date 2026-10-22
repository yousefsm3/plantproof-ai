"""A minimal fake of the Streamlit API, used only by the smoke test.

It lets app.py run top to bottom without Streamlit installed, so typos,
missing names and logic errors in the UI layer are caught early.
LIMITATION: it accepts any keyword arguments, so it cannot catch a wrong
Streamlit argument name or a rendering problem. Those can only be checked
on a real Streamlit install (e.g. Streamlit Community Cloud).
"""

from __future__ import annotations

import types
from typing import Any


class StopSignal(Exception):
    """Raised by st.stop()."""


class RerunSignal(Exception):
    """Raised by st.rerun()."""


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class FakeStreamlit:
    """Records every call. Widgets return defaults unless overridden by key/label."""

    def __init__(self, overrides: dict[str, Any] | None = None, press_buttons: bool = False,
                 log: list | None = None, session: SessionState | None = None):
        self._overrides = overrides or {}
        self._press = press_buttons
        self.calls: list[tuple[str, tuple, dict]] = log if log is not None else []
        self.session_state = session if session is not None else SessionState()

    # ---------- helpers
    def _child(self) -> "FakeStreamlit":
        return FakeStreamlit(self._overrides, self._press, self.calls, self.session_state)

    def _override(self, label, key, default):
        for k in (key, label):
            if k is not None and k in self._overrides:
                return self._overrides[k]
        return default

    def _log(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    @staticmethod
    def _fmt(options, format_func):
        if format_func:
            for o in options:
                format_func(o)  # exercise label functions for errors

    # ---------- layout / context managers
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def sidebar(self):
        return self._child()

    def columns(self, spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        self._log("columns", spec)
        return [self._child() for _ in range(n)]

    def tabs(self, labels, **kwargs):
        self._log("tabs", labels)
        return [self._child() for _ in labels]

    def expander(self, label, **kwargs):
        self._log("expander", label)
        return self._child()

    def container(self, **kwargs):
        return self._child()

    def form(self, key, **kwargs):
        self._log("form", key)
        return self._child()

    # ---------- caching decorators: @st.cache_x and @st.cache_x(...)
    def _cache(self, func=None, **kwargs):
        if callable(func):
            return func
        return lambda f: f

    cache_data = _cache
    cache_resource = _cache

    # ---------- control flow
    def stop(self):
        raise StopSignal()

    def rerun(self):
        raise RerunSignal()

    # ---------- widgets
    def radio(self, label, options, index=0, format_func=None, key=None, **kw):
        options = list(options)
        self._fmt(options, format_func)
        return self._override(label, key, options[index])

    def selectbox(self, label, options, index=0, format_func=None, key=None, **kw):
        options = list(options)
        self._fmt(options, format_func)
        value = self._override(label, key, options[index] if options else None)
        if value not in options:
            raise ValueError(f"selectbox '{label}': {value!r} not in options")
        return value

    def multiselect(self, label, options, default=None, format_func=None, key=None, **kw):
        options = list(options)
        self._fmt(options, format_func)
        value = self._override(label, key, list(default or []))
        bad = [v for v in value if v not in options]
        if bad:
            raise ValueError(f"multiselect '{label}': {bad} not in options")
        return value

    def checkbox(self, label, value=False, key=None, **kw):
        return self._override(label, key, value)

    def text_input(self, label, value="", key=None, **kw):
        return self._override(label, key, value)

    def text_area(self, label, value="", key=None, **kw):
        return self._override(label, key, value)

    def number_input(self, label, min_value=None, max_value=None, value=None, key=None, **kw):
        v = self._override(label, key, value if value is not None else (min_value or 0.0))
        if min_value is not None and v < min_value:
            raise ValueError(f"number_input '{label}': {v} < min {min_value}")
        return v

    def slider(self, label, min_value=None, max_value=None, value=None, step=None, key=None, **kw):
        return self._override(label, key, value if value is not None else min_value)

    def file_uploader(self, label, key=None, **kw):
        return self._override(label, key, None)

    def button(self, label, key=None, disabled=False, **kw):
        self._log("button", label)
        return False if disabled else self._override(label, key, self._press)

    def form_submit_button(self, label="Submit", **kw):
        self._log("form_submit_button", label)
        return self._override(label, None, self._press)

    def download_button(self, label, data, file_name=None, **kw):
        if not isinstance(data, (str, bytes)):
            raise TypeError(f"download_button '{label}': data must be str or bytes")
        if not file_name:
            raise ValueError(f"download_button '{label}': file_name missing")
        self._log("download_button", label, file_name=file_name, size=len(data))
        return False

    # ---------- everything else (markdown, metric, dataframe, plotly_chart ...)
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            self._log(name, *args, **kwargs)
            return self._child()
        return call


class _Stub:
    """Stands in for any Plotly object; every method call returns the stub."""

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: self


def make_plotly_modules() -> dict[str, types.ModuleType]:
    plotly = types.ModuleType("plotly")
    go = types.ModuleType("plotly.graph_objects")
    for cls in ("Figure", "Bar", "Scatter"):
        setattr(go, cls, _Stub)
    plotly.graph_objects = go
    return {"plotly": plotly, "plotly.graph_objects": go}
