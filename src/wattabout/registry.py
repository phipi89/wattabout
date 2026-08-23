from __future__ import annotations

from collections.abc import Iterator

from .core import Asset, WattAboutError


class CategoryNamespace:
    def __init__(self, registry: Registry, category: str) -> None:
        self._registry = registry
        self._category = category

    def __getattr__(self, name: str) -> Asset:
        try:
            return self._registry.get(f"{self._category}.{name}")
        except WattAboutError as error:
            raise AttributeError(f"Category {self._category!r} has no asset {name!r}") from error

    def __dir__(self) -> list[str]:
        return sorted({*super().__dir__(), *self.assets()})

    def __iter__(self) -> Iterator[Asset]:
        return iter(self._registry.assets(self._category))

    def __repr__(self) -> str:
        return f"<AssetCategory {self._category}: {', '.join(self.assets())}>"

    def assets(self) -> tuple[str, ...]:
        prefix = f"{self._category}."
        return tuple(
            asset.id.removeprefix(prefix) for asset in self._registry.assets(self._category)
        )


class Registry:
    def __init__(self) -> None:
        self._assets: dict[str, Asset] = {}

    def register(self, asset: Asset) -> Asset:
        segments = asset.id.split(".")
        if len(segments) != 2 or not all(segment.isidentifier() for segment in segments):
            raise WattAboutError(f"Asset ID {asset.id!r} must have the form 'category.name'")
        if asset.id in self._assets:
            raise WattAboutError(f"Asset {asset.id!r} is already registered")
        self._assets[asset.id] = asset
        return asset

    def get(self, asset_id: str) -> Asset:
        try:
            return self._assets[asset_id]
        except KeyError as error:
            raise WattAboutError(f"Unknown asset {asset_id!r}") from error

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({asset.category for asset in self._assets.values()}))

    def assets(self, category: str | None = None) -> tuple[Asset, ...]:
        selected = (
            self._assets.values()
            if category is None
            else (asset for asset in self._assets.values() if asset.category == category)
        )
        return tuple(sorted(selected, key=lambda asset: asset.id))

    def namespace(self, category: str) -> CategoryNamespace:
        if category not in self.categories():
            raise WattAboutError(f"Unknown asset category {category!r}")
        return CategoryNamespace(self, category)

    def __iter__(self) -> Iterator[Asset]:
        return iter(self._assets.values())

    def __len__(self) -> int:
        return len(self._assets)
