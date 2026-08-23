from ..registry import Registry
from .building import ASSETS as BUILDING_ASSETS
from .electronics import ASSETS as ELECTRONICS_ASSETS
from .energy import ASSETS as ENERGY_ASSETS
from .food import ASSETS as FOOD_ASSETS
from .heating import ASSETS as HEATING_ASSETS
from .household import ASSETS as HOUSEHOLD_ASSETS
from .transport import ASSETS as TRANSPORT_ASSETS

registry = Registry()

for asset in (
    *TRANSPORT_ASSETS,
    *BUILDING_ASSETS,
    *ELECTRONICS_ASSETS,
    *FOOD_ASSETS,
    *HOUSEHOLD_ASSETS,
    *HEATING_ASSETS,
    *ENERGY_ASSETS,
):
    registry.register(asset)
