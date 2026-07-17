"""
Levi AI — Administrative Tier Authority Rules

Single source of truth for the 4-tier hierarchy. Every route and
dependency that needs to answer "can this admin act on that admin"
imports from here, so the rules only ever live in one place.

Tiers (lower number = more authority):
    1  owner        — System Owner, unrestricted, untouchable
    2  super_admin   — Super Admin, executive authority
    3  admin         — Administrator, departmental authority
    4  moderator     — Moderator, user moderation only
"""

TIER_RANK = {
    "owner": 1,
    "super_admin": 2,
    "admin": 3,
    "moderator": 4,
}

TIER_LABELS = {
    "owner": "System Owner",
    "super_admin": "Super Admin",
    "admin": "Administrator",
    "moderator": "Moderator",
}

PLATFORM_ROLES = [
    "technical",
    "operations",
    "finance",
    "analytics",
    "support",
    "communications",
]

VALID_TIERS = set(TIER_RANK.keys())


def rank(tier: str) -> int:
    """Lower number = higher authority. Unknown tier ranks lowest (safest default)."""
    return TIER_RANK.get(tier, 999)


def visible_tiers_for(actor_tier: str):
    """
    Which tiers appear in the Admins directory for this viewer.
    Returns None if the viewer has no access to the Admins module at all.
    """
    if actor_tier in ("owner", "super_admin"):
        return {"owner", "super_admin", "admin", "moderator"}
    if actor_tier == "admin":
        return {"admin", "moderator"}
    return None  # moderator — no admin module access


def can_create(actor_tier: str, target_tier: str) -> bool:
    """Can actor create a new admin account at target_tier?"""
    if actor_tier == "owner":
        # Owner can create anyone except another Owner — there is only
        # ever one Tier 1 account, and it isn't created through the API.
        return target_tier in ("super_admin", "admin", "moderator")
    if actor_tier == "super_admin":
        return target_tier in ("admin", "moderator")
    return False  # admin, moderator cannot create anyone


def can_manage(actor_tier: str, target_tier: str) -> bool:
    """
    Can actor suspend/unsuspend/delete/edit the target admin account?
    (The baseline "act on another admin" check.)
    """
    if actor_tier == "owner":
        return target_tier != "owner"
    if actor_tier == "super_admin":
        return target_tier in ("admin", "moderator")
    if actor_tier == "admin":
        return target_tier == "moderator"
    return False  # moderator can never manage another admin


def can_promote_demote(actor_tier: str, target_tier: str, new_tier: str) -> bool:
    """Can actor change target_tier's tier to new_tier?"""
    if new_tier == "owner":
        # Ownership transfer is a deliberate, out-of-band action —
        # never available through the promote/demote endpoint.
        return False

    if actor_tier == "owner":
        # Owner may set any non-owner admin to any non-owner tier.
        return target_tier != "owner" and new_tier in ("super_admin", "admin", "moderator")

    if actor_tier == "super_admin":
        # Only allowed to swap Tier 3 <-> Tier 4, on Tier 3/4 targets.
        return target_tier in ("admin", "moderator") and new_tier in ("admin", "moderator")

    return False  # admin, moderator cannot promote/demote anyone


def can_delete_user(actor_tier: str) -> bool:
    """Permanent user deletion — restricted to the top two tiers."""
    return actor_tier in ("owner", "super_admin")
