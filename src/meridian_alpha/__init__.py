from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from types import ModuleType

_LEGACY_ROOT = "enhengclaw"
_ALIAS_ROOT = __name__


def _target_name_for(fullname: str) -> str:
    prefix = f"{_ALIAS_ROOT}."
    if fullname == _ALIAS_ROOT:
        return _LEGACY_ROOT
    return f"{_LEGACY_ROOT}.{fullname.removeprefix(prefix)}"


class _AliasLoader(importlib.abc.InspectLoader):
    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        target_name = str(spec.loader_state["target_name"])
        target_module = importlib.import_module(target_name)
        sys.modules[spec.name] = target_module
        return target_module

    def exec_module(self, module: ModuleType) -> None:
        return None

    def get_code(self, fullname: str):
        target_spec = _target_spec_for(fullname)
        loader = target_spec.loader
        if hasattr(loader, "get_code"):
            return loader.get_code(_target_name_for(fullname))
        source = self.get_source(fullname)
        if source is None:
            return None
        return compile(source, self.get_filename(fullname), "exec")

    def get_source(self, fullname: str) -> str | None:
        target_spec = _target_spec_for(fullname)
        loader = target_spec.loader
        if hasattr(loader, "get_source"):
            return loader.get_source(_target_name_for(fullname))
        return None

    def get_filename(self, fullname: str) -> str:
        target_spec = _target_spec_for(fullname)
        origin = target_spec.origin
        if origin is None:
            raise ImportError(f"cannot resolve filename for module alias {fullname!r}")
        return origin

    def is_package(self, fullname: str) -> bool:
        target_spec = _target_spec_for(fullname)
        return target_spec.submodule_search_locations is not None


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: object | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        prefix = f"{_ALIAS_ROOT}."
        if not fullname.startswith(prefix):
            return None
        target_name = _target_name_for(fullname)
        target_spec = importlib.util.find_spec(target_name)
        if target_spec is None:
            return None
        spec = importlib.machinery.ModuleSpec(
            fullname,
            _AliasLoader(),
            is_package=target_spec.submodule_search_locations is not None,
        )
        spec.loader_state = {"target_name": target_name}
        spec.origin = target_spec.origin
        spec.has_location = bool(target_spec.has_location)
        spec.submodule_search_locations = target_spec.submodule_search_locations
        return spec


def _install_alias_finder() -> None:
    if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())


def _target_spec_for(fullname: str) -> importlib.machinery.ModuleSpec:
    target_name = _target_name_for(fullname)
    target_spec = importlib.util.find_spec(target_name)
    if target_spec is None:
        raise ImportError(f"cannot resolve module alias {fullname!r} to {target_name!r}")
    return target_spec


_legacy = importlib.import_module(_LEGACY_ROOT)
_install_alias_finder()

__all__ = getattr(_legacy, "__all__", ())
__version__ = getattr(_legacy, "__version__", "0.1.0")
__path__ = _legacy.__path__


def __getattr__(name: str) -> object:
    return getattr(_legacy, name)
