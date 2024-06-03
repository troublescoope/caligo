from typing import TYPE_CHECKING, Any

import dns.resolver

from .base import CaligoBase
from .database import AsyncClient, AsyncDatabase

if TYPE_CHECKING:
    from .bot import Caligo


class DatabaseProvider(CaligoBase):
    db: AsyncDatabase

    def __init__(self: "Caligo", **kwargs: Any) -> None:
        # Check if DNS configuration is provided and has value
        db_dns: list = [self.config["bot"].get("db_dns")]
        if db_dns:
            dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
            dns.resolver.default_resolver.nameservers = db_dns

        client = AsyncClient(self.config["bot"]["db_uri"], connect=False)
        self.db = client.get_database("CALIGO")

        # Propagate initialization to other mixins
        super().__init__(**kwargs)
