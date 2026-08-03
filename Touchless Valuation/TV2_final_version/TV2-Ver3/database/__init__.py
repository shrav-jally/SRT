"""
database — SQLite3 data access layer for Touchless Valuation : E-Vardhan.

Exposes comparable-company data, sector taxonomy, dataset metadata,
and user tracking / access control from two databases:
    comps_v2.db      — company comparable data (read-only for tool logic)
    TV_E-Vardhan.db  — users, transaction data, company mirror (read-write)
"""

from .data import (load_comparables, sectors_with_availability, dataset_meta,
                   reset_cache, AS_OF, MULTIPLE_SOURCE)

from .user_db import (
    init_user_db,
    check_user_access,
    update_last_login,
    add_user,
    delete_user,
    get_all_users,
    new_trial_uuid,
    log_transaction,
    log_trial,
    get_transaction_data,
    get_search_data,
    get_all_search_data,
    get_all_companies,
    refresh_companies,
    admin_overview,
)

__all__ = [
    # comps data
    "load_comparables",
    "sectors_with_availability",
    "dataset_meta",
    "reset_cache",
    "AS_OF",
    "MULTIPLE_SOURCE",
    # user tracking
    "init_user_db",
    "check_user_access",
    "update_last_login",
    "add_user",
    "delete_user",
    "get_all_users",
    "new_trial_uuid",
    "log_transaction",
    "log_trial",
    "get_transaction_data",
    "get_search_data",
    "get_all_search_data",
    "get_all_companies",
    "refresh_companies",
    "admin_overview",
]
