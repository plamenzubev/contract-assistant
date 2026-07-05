from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    """
    Enables the pgvector extension in the database (CREATE EXTENSION vector).
    Runs BEFORE the migration that creates the table with the vector column.

    Note: the initial CREATE EXTENSION requires superuser privileges. If
    contract_user doesn't have them, enable the extension once as a superuser
    (see the instructions) — then this operation is a harmless no-op.
    """

    dependencies = [
        ("contracts", "0001_initial"),
    ]

    operations = [
        VectorExtension(),
    ]
