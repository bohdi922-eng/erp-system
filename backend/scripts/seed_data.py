"""Seed the database with data matching the Stitch design concepts, so the
running app looks like the mockups on first launch.

Run from backend/: `python -m scripts.seed_data`

This deliberately calls the SERVICE functions (not raw model inserts) for
customers/items/invoices/repairs — it doubles as a smoke test that
crm_service / inventory_service / sales_service / repairs_service actually
work end-to-end after the bug fixes made during the code review.
"""
from __future__ import annotations

from decimal import Decimal

from app.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models import Product, ShopSettings, User
from app.services import crm_service, inventory_service, repairs_service, sales_service


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        # -- Users (matches the Settings screen mockup) ---------------------
        # All seeded users share the same demo password so the app is easy
        # to explore after a fresh install. Change them via the Settings
        # screen (or the /api/settings/users endpoint) before going live.
        demo_password = "1234"
        users = {
            "ahmed": User(
                username="ahmed.m", full_name="أحمد محمود", role="admin",
                password_hash=hash_password(demo_password),
            ),
            "khaled": User(
                username="khaled.s", full_name="خالد سعيد", role="cashier",
                password_hash=hash_password(demo_password),
            ),
            "salem": User(
                username="salem.a", full_name="سالم علي", role="technician",
                password_hash=hash_password(demo_password),
            ),
        }
        for u in users.values():
            db.add(u)
        db.flush()

        # -- Products (matches items seen across the POS/inventory mockups) -
        products = {
            "screen_ip13pm": Product(
                brand="Apple", model="شاشة ايفون 13 برو ماكس أصلي",
                is_serialized=True, default_price=Decimal("3500.00"),
                warranty_months=3,
            ),
            "battery_s22u": Product(
                brand="Samsung", model="بطارية سامسونج S22 Ultra",
                is_serialized=True, default_price=Decimal("850.00"),
                warranty_months=6,
            ),
            "iphone14pro": Product(
                brand="Apple", model="iPhone 14 Pro",
                is_serialized=True, default_price=Decimal("32000.00"),
                warranty_months=12,
            ),
            "macbook_m2": Product(
                brand="Apple", model="MacBook Pro M2",
                is_serialized=True, default_price=Decimal("58000.00"),
                warranty_months=12,
            ),
            "ipad_air5": Product(
                brand="Apple", model="iPad Air 5",
                is_serialized=True, default_price=Decimal("21000.00"),
                warranty_months=12,
            ),
            "ps5": Product(
                brand="Sony", model="PlayStation 5",
                is_serialized=True, default_price=Decimal("19500.00"),
                warranty_months=12,
            ),
            "screen_protector_ip13": Product(
                brand="Generic", model="لاصقة حماية زجاجية ايفون 13/13 برو",
                is_serialized=False, default_price=Decimal("114.00"),
                warranty_months=0,
            ),
        }
        for p in products.values():
            db.add(p)
        db.flush()

        # -- Physical stock (Items) for the serialized products -------------
        screen_item = inventory_service.create_item(
            db, product_id=products["screen_ip13pm"].id,
            serial_number="SCR-IP13PM-001", purchase_cost=Decimal("2600.00"),
            user_id=users["khaled"].id,
        )
        battery_item = inventory_service.create_item(
            db, product_id=products["battery_s22u"].id,
            serial_number="BAT-SS22U-042", purchase_cost=Decimal("500.00"),
            user_id=users["khaled"].id,
        )
        inventory_service.create_item(
            db, product_id=products["iphone14pro"].id,
            serial_number="F4G9H8J7K6L5", purchase_cost=Decimal("27000.00"),
            user_id=users["khaled"].id,
        )
        inventory_service.create_item(
            db, product_id=products["macbook_m2"].id,
            serial_number="MBP-M2-0091", purchase_cost=Decimal("50000.00"),
            user_id=users["khaled"].id,
        )

        # -- Shop settings (matches the corrected settings.html mockup) ----
        db.add(ShopSettings(
            name="متجر الإلكترونيات", tax_id="123456789",
            address="القاهرة، مدينة نصر، شارع عباس العقاد",
            phone="+20 100 123 4567", email="info@erp-system.example",
        ))

        # -- Customers --------------------------------------------------------
        acme = crm_service.create_customer(
            db, name="شركة الأفق الذهبي للتجارة", phone="01012345678",
            address="القاهرة، مدينة نصر", tax_id="CUST-2023-0892",
            credit_limit=Decimal("50000.00"),
        )
        omar = crm_service.create_customer(db, name="عمر طارق", phone="01098765432")
        sara = crm_service.create_customer(db, name="سارة يوسف", phone="01055512345")
        khaled_c = crm_service.create_customer(db, name="خالد عبدالله", phone="01055598765")
        ahmed_f = crm_service.create_customer(db, name="أحمد فتحي", phone="01011122233")

        # Two walk-in customers with NO phone — regression test for the
        # empty-string-vs-NULL unique constraint bug fixed in
        # crm_service.create_customer(). Both must succeed; the second one
        # failing would mean the fix regressed.
        walkin_1 = crm_service.get_or_create_customer(db, name="عميل نقدي")
        walkin_2 = crm_service.get_or_create_customer(db, name="عميل نقدي 2")
        assert walkin_1.id != walkin_2.id, "walk-in customers collapsed into one row unexpectedly"

        # -- Repair center ------------------------------------------------
        center = repairs_service.create_repair_center(
            db, name="مركز الصيانة الخارجي المعتمد", phone="0223456789",
        )

        # -- The POS invoice matching the sales_new_invoice.html mockup ----
        sales_service.create_invoice(
            db,
            customer_id=acme.id,
            lines=[
                {"item_uuid": screen_item.uuid, "quantity": 1, "unit_price": Decimal("3500.00")},
                {"item_uuid": battery_item.uuid, "quantity": 2, "unit_price": Decimal("850.00")},
            ],
            payments=[{"amount": Decimal("5928.00"), "method": "cash"}],
            user_id=users["khaled"].id,
        )

        # -- Repairs matching the Kanban board mockup -----------------------
        rep_8088 = repairs_service.receive_device(
            db, customer_id=sara.id, device_description="MacBook Pro M2",
            reported_issue="لوحة أم", user_id=users["khaled"].id,
        )
        repairs_service.hand_to_technician(
            db, rep_8088.id, technician_id=users["salem"].id, user_id=users["khaled"].id,
        )

        rep_8090 = repairs_service.receive_device(
            db, customer_id=khaled_c.id, device_description="iPad Air 5",
            reported_issue="منفذ شحن", user_id=users["khaled"].id,
        )
        repairs_service.hand_to_technician(
            db, rep_8090.id, technician_id=users["salem"].id, user_id=users["khaled"].id,
        )

        repairs_service.receive_device(
            db, customer_id=ahmed_f.id, device_description="iPhone 14 Pro",
            reported_issue="شاشة", user_id=users["khaled"].id,
        )

        repairs_service.receive_device(
            db, customer_id=acme.id, device_description="Samsung Galaxy S22",
            reported_issue="بطارية", user_id=users["khaled"].id,
        )

        rep_8075 = repairs_service.receive_device(
            db, customer_id=omar.id, device_description="PlayStation 5",
            reported_issue="صيانة عامة", user_id=users["khaled"].id,
        )
        repairs_service.hand_to_technician(
            db, rep_8075.id, technician_id=users["salem"].id, user_id=users["khaled"].id,
        )
        repairs_service.receive_from_technician(
            db, rep_8075.id, actual_cost=Decimal("450.00"),
            repair_result="تم تنظيف الوحدة واستبدال المروحة",
            user_id=users["salem"].id,
        )
        repairs_service.deliver_repair(
            db, rep_8075.id, shop_fee=Decimal("0.00"), user_id=users["khaled"].id,
        )

        db.commit()
        print("Seed complete.")
        print(f"  Users: {len(users)}")
        print(f"  Products: {len(products)}")
        print(f"  Customers: {[acme.name, omar.name, sara.name, khaled_c.name, ahmed_f.name, walkin_1.name, walkin_2.name]}")
        print(f"  Repair center: {center.name}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
