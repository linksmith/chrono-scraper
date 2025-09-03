"""Add ON DELETE rules for foreign keys referencing pages.id

Revision ID: c2f4a7d1b9a0
Revises: b4912847f99c
Create Date: 2025-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c2f4a7d1b9a0'
down_revision: Union[str, None] = 'b4912847f99c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # starred_items.page_id -> pages.id ON DELETE CASCADE
    try:
        op.drop_constraint('starred_items_page_id_fkey', 'starred_items', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'starred_items_page_id_fkey', 'starred_items', 'pages', ['page_id'], ['id'], ondelete='CASCADE'
    )

    # content_extractions.page_id -> pages.id ON DELETE CASCADE
    try:
        op.drop_constraint('content_extractions_page_id_fkey', 'content_extractions', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'content_extractions_page_id_fkey', 'content_extractions', 'pages', ['page_id'], ['id'], ondelete='CASCADE'
    )

    # extracted_entities.page_id -> pages.id ON DELETE CASCADE
    try:
        op.drop_constraint('extracted_entities_page_id_fkey', 'extracted_entities', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'extracted_entities_page_id_fkey', 'extracted_entities', 'pages', ['page_id'], ['id'], ondelete='CASCADE'
    )

    # entity_mentions.page_id -> pages.id ON DELETE CASCADE
    try:
        op.drop_constraint('entity_mentions_page_id_fkey', 'entity_mentions', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'entity_mentions_page_id_fkey', 'entity_mentions', 'pages', ['page_id'], ['id'], ondelete='CASCADE'
    )

    # evidence.page_id -> pages.id ON DELETE SET NULL
    try:
        op.drop_constraint('evidence_page_id_fkey', 'evidence', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'evidence_page_id_fkey', 'evidence', 'pages', ['page_id'], ['id'], ondelete='SET NULL'
    )

    # page_comparisons.baseline_page_id -> pages.id ON DELETE CASCADE
    try:
        op.drop_constraint('page_comparisons_baseline_page_id_fkey', 'page_comparisons', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'page_comparisons_baseline_page_id_fkey', 'page_comparisons', 'pages', ['baseline_page_id'], ['id'], ondelete='CASCADE'
    )

    # page_comparisons.target_page_id -> pages.id ON DELETE CASCADE
    try:
        op.drop_constraint('page_comparisons_target_page_id_fkey', 'page_comparisons', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'page_comparisons_target_page_id_fkey', 'page_comparisons', 'pages', ['target_page_id'], ['id'], ondelete='CASCADE'
    )

    # investigation_timelines.page_id -> pages.id ON DELETE SET NULL
    try:
        op.drop_constraint('investigation_timelines_page_id_fkey', 'investigation_timelines', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'investigation_timelines_page_id_fkey', 'investigation_timelines', 'pages', ['page_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    # investigation_timelines.page_id -> pages.id NO ACTION
    op.drop_constraint('investigation_timelines_page_id_fkey', 'investigation_timelines', type_='foreignkey')
    op.create_foreign_key(
        'investigation_timelines_page_id_fkey', 'investigation_timelines', 'pages', ['page_id'], ['id'], ondelete='NO ACTION'
    )

    # page_comparisons.target_page_id -> pages.id NO ACTION
    op.drop_constraint('page_comparisons_target_page_id_fkey', 'page_comparisons', type_='foreignkey')
    op.create_foreign_key(
        'page_comparisons_target_page_id_fkey', 'page_comparisons', 'pages', ['target_page_id'], ['id'], ondelete='NO ACTION'
    )

    # page_comparisons.baseline_page_id -> pages.id NO ACTION
    op.drop_constraint('page_comparisons_baseline_page_id_fkey', 'page_comparisons', type_='foreignkey')
    op.create_foreign_key(
        'page_comparisons_baseline_page_id_fkey', 'page_comparisons', 'pages', ['baseline_page_id'], ['id'], ondelete='NO ACTION'
    )

    # evidence.page_id -> pages.id NO ACTION
    op.drop_constraint('evidence_page_id_fkey', 'evidence', type_='foreignkey')
    op.create_foreign_key(
        'evidence_page_id_fkey', 'evidence', 'pages', ['page_id'], ['id'], ondelete='NO ACTION'
    )

    # entity_mentions.page_id -> pages.id NO ACTION
    op.drop_constraint('entity_mentions_page_id_fkey', 'entity_mentions', type_='foreignkey')
    op.create_foreign_key(
        'entity_mentions_page_id_fkey', 'entity_mentions', 'pages', ['page_id'], ['id'], ondelete='NO ACTION'
    )

    # extracted_entities.page_id -> pages.id NO ACTION
    op.drop_constraint('extracted_entities_page_id_fkey', 'extracted_entities', type_='foreignkey')
    op.create_foreign_key(
        'extracted_entities_page_id_fkey', 'extracted_entities', 'pages', ['page_id'], ['id'], ondelete='NO ACTION'
    )

    # content_extractions.page_id -> pages.id NO ACTION
    op.drop_constraint('content_extractions_page_id_fkey', 'content_extractions', type_='foreignkey')
    op.create_foreign_key(
        'content_extractions_page_id_fkey', 'content_extractions', 'pages', ['page_id'], ['id'], ondelete='NO ACTION'
    )

    # starred_items.page_id -> pages.id NO ACTION
    op.drop_constraint('starred_items_page_id_fkey', 'starred_items', type_='foreignkey')
    op.create_foreign_key(
        'starred_items_page_id_fkey', 'starred_items', 'pages', ['page_id'], ['id'], ondelete='NO ACTION'
    )



