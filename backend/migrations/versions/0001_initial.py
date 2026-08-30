"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- No foreign keys ---------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="warehouse"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(120), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("categories.id"), nullable=True),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(120), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("tax_id", sa.String(40), nullable=True),
        sa.Column("credit_limit", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("phone", name="uq_customers_phone"),
    )

    op.create_table(
        "repair_centers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(120), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("phone", name="uq_repair_centers_phone"),
    )

    op.create_table(
        "shop_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, server_default="متجر الإلكترونيات"),
        sa.Column("tax_id", sa.String(40), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(120), nullable=True),
    )

    op.create_table(
        "document_sequences",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("doc_type", sa.String(20), nullable=False, unique=True),
        sa.Column("last_number", sa.Integer, nullable=False, server_default="0"),
    )

    # -- Depends on: categories ---------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("brand", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("is_serialized", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("default_price", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("warranty_months", sa.Integer, nullable=False, server_default="0"),
        sa.Column("warranty_terms", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    # -- Depends on: suppliers ------------------------------------------
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("order_date", sa.Date, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # -- Depends on: products, locations, suppliers -------------------------
    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uuid", sa.String(32), nullable=False, unique=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("serial_number", sa.String(120), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_stock"),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("purchase_cost", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("purchase_date", sa.Date, nullable=False),
        sa.Column("warranty_months", sa.Integer, nullable=False, server_default="0"),
        sa.Column("warranty_terms", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # -- Depends on: purchase_orders, products -------------------------
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("purchase_id", sa.Integer, sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
    )

    # -- Depends on: items, locations, users --------------------------------
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("ref_type", sa.String(20), nullable=True),
        sa.Column("ref_id", sa.Integer, nullable=True),
        sa.Column("from_location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("to_location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # -- Depends on: customers, users -----------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("invoice_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=False, server_default="0.00"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # -- Depends on: invoices, items, products -----------------------------
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("invoice_id", sa.Integer, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
    )

    # -- Depends on: invoices, purchase_orders, customers, suppliers, users --
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("invoice_id", sa.Integer, sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("purchase_id", sa.Integer, sa.ForeignKey("purchase_orders.id"), nullable=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_at", sa.DateTime, nullable=False),
        sa.Column("method", sa.String(20), nullable=False, server_default="cash"),
        sa.Column("reference", sa.String(80), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )

    # -- Depends on: invoices, customers, users -----------------------------
    op.create_table(
        "sales_returns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("invoice_id", sa.Integer, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("return_date", sa.Date, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )

    # -- Depends on: sales_returns, items -----------------------------------
    op.create_table(
        "sales_return_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sale_return_id", sa.Integer, sa.ForeignKey("sales_returns.id"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
    )

    # -- Depends on: customers, items, repair_centers, users, invoices ------
    op.create_table(
        "repair_orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=True),
        sa.Column("device_description", sa.Text, nullable=False),
        sa.Column("reported_issue", sa.Text, nullable=False),
        sa.Column("condition_received", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("repair_center_id", sa.Integer, sa.ForeignKey("repair_centers.id"), nullable=True),
        sa.Column("external_tracking", sa.String(80), nullable=True),
        sa.Column("expected_cost", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("technician_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("handed_to_tech_at", sa.DateTime, nullable=True),
        sa.Column("received_from_tech_at", sa.DateTime, nullable=True),
        sa.Column("returned_at", sa.DateTime, nullable=True),
        sa.Column("actual_cost", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("repair_result", sa.Text, nullable=True),
        sa.Column("invoice_id", sa.Integer, sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("shop_fee", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    # Reverse dependency order.
    op.drop_table("repair_orders")
    op.drop_table("sales_return_lines")
    op.drop_table("sales_returns")
    op.drop_table("payments")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
    op.drop_table("stock_movements")
    op.drop_table("purchase_order_lines")
    op.drop_table("items")
    op.drop_table("purchase_orders")
    op.drop_table("products")
    op.drop_table("document_sequences")
    op.drop_table("shop_settings")
    op.drop_table("repair_centers")
    op.drop_table("customers")
    op.drop_table("categories")
    op.drop_table("suppliers")
    op.drop_table("locations")
    op.drop_table("users")
