"""Stylebook domain logic shared by worker, stylebook-api, and core-api."""

from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
)
from backfield_stylebook.canonical.policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
    decide_canonical_persist_plan,
    find_existing_canonical_id_by_alias,
    rank_scored_canonical_recall_matches,
)
from backfield_stylebook.entities.location.persist import (
    apply_canonical_persist_plan,
    assert_canonical_link_invariant,
    create_standalone_canonical,
    link_to_existing_canonical,
    materialize_new_canonical_and_link,
    refresh_aliases_for_linked_location,
    sync_substrate_location_into_stylebook,
)
from backfield_stylebook.entities.person import (
    apply_canonical_persist_plan as apply_person_canonical_persist_plan,
)
from backfield_stylebook.entities.person import (
    create_standalone_canonical as create_standalone_person_canonical,
)
from backfield_stylebook.entities.person import (
    decide_person_canonical_persist_plan,
    find_existing_person_canonical_id_by_alias,
    person_identity_fingerprint,
    rank_canonical_suggestions_for_substrate,
    sync_substrate_person_into_stylebook,
)
from backfield_stylebook.entities.person import (
    link_to_existing_canonical as link_person_to_existing_canonical,
)
from backfield_stylebook.entities.person import (
    materialize_new_canonical_and_link as materialize_new_person_canonical_and_link,
)
from backfield_stylebook.entity_types import (
    EntityMeta,
    EntityType,
    all_entity_types,
    compute_identity_fingerprint,
    consolidated_key_for,
    entity_meta,
    entity_type_from_consolidated_key,
    normalize_entity_name,
)
from backfield_stylebook.full_bundle import (
    ALLOWED_MANIFEST_SCHEMA_VERSIONS,
    BUNDLE_SCHEMA_VERSION,
    DEFAULT_MAX_ZIP_BYTES,
    export_stylebook_bundle,
    import_stylebook_bundle,
    read_manifest_from_zip,
)
from backfield_stylebook.graph_stylebook_refs import (
    STYLEBOOK_NODE_PARAM_KEY,
    StylebookGraphRefsError,
    count_stylebook_usage_in_graphs,
    iter_stylebook_refs_from_spec_dict,
    unique_stylebook_ids_from_spec_dict,
    validate_stylebook_refs_for_organization,
)
from backfield_stylebook.resolve import (
    STYLEBOOK_SLUG_NOT_IN_ORG,
    resolve_effective_stylebook_id_for_project,
    resolve_stylebook_id_for_project_id,
)
from backfield_stylebook.stylebook_library import (
    StylebookLibraryError,
    create_stylebook,
    delete_stylebook,
    rename_stylebook,
    resolve_stylebook_by_slug,
    set_org_default_stylebook,
)
from backfield_stylebook.stylebook_record_slug import (
    allocate_unique_stylebook_slug,
    slugify_stylebook_name,
)

__all__ = [
    "ALLOWED_MANIFEST_SCHEMA_VERSIONS",
    "BUNDLE_SCHEMA_VERSION",
    "DEFAULT_MAX_ZIP_BYTES",
    "CANONICAL_LINK_LINKED",
    "CANONICAL_LINK_PENDING",
    "CANONICAL_LINK_UNLINKED",
    "CANONICAL_LINK_WAIVED",
    "CanonicalPersistDecision",
    "CanonicalPersistPlan",
    "apply_canonical_persist_plan",
    "apply_person_canonical_persist_plan",
    "assert_canonical_link_invariant",
    "create_standalone_canonical",
    "create_standalone_person_canonical",
    "decide_canonical_persist_plan",
    "decide_person_canonical_persist_plan",
    "STYLEBOOK_NODE_PARAM_KEY",
    "StylebookGraphRefsError",
    "StylebookLibraryError",
    "allocate_unique_stylebook_slug",
    "count_stylebook_usage_in_graphs",
    "create_stylebook",
    "delete_stylebook",
    "EntityMeta",
    "EntityType",
    "all_entity_types",
    "compute_identity_fingerprint",
    "consolidated_key_for",
    "entity_meta",
    "entity_type_from_consolidated_key",
    "normalize_entity_name",
    "export_stylebook_bundle",
    "ensure_default_stylebook_for_organization",
    "iter_stylebook_refs_from_spec_dict",
    "find_existing_canonical_id_by_alias",
    "find_existing_person_canonical_id_by_alias",
    "import_stylebook_bundle",
    "rank_scored_canonical_recall_matches",
    "link_to_existing_canonical",
    "link_person_to_existing_canonical",
    "materialize_new_canonical_and_link",
    "materialize_new_person_canonical_and_link",
    "person_identity_fingerprint",
    "rank_canonical_suggestions_for_substrate",
    "read_manifest_from_zip",
    "refresh_aliases_for_linked_location",
    "rename_stylebook",
    "resolve_stylebook_by_slug",
    "resolve_effective_stylebook_id_for_project",
    "resolve_stylebook_id_for_project_id",
    "STYLEBOOK_SLUG_NOT_IN_ORG",
    "set_org_default_stylebook",
    "slugify_stylebook_name",
    "unique_stylebook_ids_from_spec_dict",
    "sync_substrate_location_into_stylebook",
    "sync_substrate_person_into_stylebook",
    "validate_stylebook_refs_for_organization",
]
