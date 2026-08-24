from ..registry import Registry
from .ai import ASSETS as AI_ASSETS
from .buildings import ASSETS as BUILDING_ASSETS
from .electronics import ASSETS as ELECTRONICS_ASSETS
from .energy import ASSETS as ENERGY_ASSETS
from .food import ASSETS as FOOD_ASSETS
from .heating import ASSETS as HEATING_ASSETS
from .household import ASSETS as HOUSEHOLD_ASSETS
from .lifestyle import ASSETS as LIFESTYLE_ASSETS
from .nature import ASSETS as NATURE_ASSETS
from .shipping import ASSETS as SHIPPING_ASSETS
from .transport import ASSETS as TRANSPORT_ASSETS
from .waste import ASSETS as WASTE_ASSETS

registry = Registry()

for asset in (
    *AI_ASSETS,
    *TRANSPORT_ASSETS,
    *BUILDING_ASSETS,
    *ELECTRONICS_ASSETS,
    *FOOD_ASSETS,
    *HOUSEHOLD_ASSETS,
    *HEATING_ASSETS,
    *ENERGY_ASSETS,
    *LIFESTYLE_ASSETS,
    *NATURE_ASSETS,
    *SHIPPING_ASSETS,
    *WASTE_ASSETS,
):
    registry.register(asset)
