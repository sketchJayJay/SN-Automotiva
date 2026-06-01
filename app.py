from __future__ import annotations

import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Any

from flask import Flask, flash, g, make_response, redirect, render_template, request, send_from_directory, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE = Path(os.environ.get("DATABASE_PATH", DATA_DIR / "sn_servicos.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "sn-servicos-automotivos-dev")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def money_to_float(value: str | None) -> float:
    if not value:
        return 0.0
    cleaned = value.strip().replace("R$", "").replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def float_to_money(value: float | int | None) -> str:
    value = float(value or 0)
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def today_iso() -> str:
    return date.today().isoformat()


def br_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def br_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y às %H:%M")
    except ValueError:
        return value


def query_one(sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, args).fetchone()


def query_all(sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, args).fetchall()


def execute(sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            document TEXT,
            address TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            plate TEXT,
            brand TEXT,
            model TEXT,
            year TEXT,
            color TEXT,
            km INTEGER DEFAULT 0,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            unit_price REAL DEFAULT 0,
            qty REAL DEFAULT 0,
            min_qty REAL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS service_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Aberta',
            km_atual INTEGER DEFAULT 0,
            description TEXT,
            labor_value REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            inventory_id INTEGER,
            name TEXT NOT NULL,
            qty REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            total REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES service_orders(id) ON DELETE CASCADE,
            FOREIGN KEY (inventory_id) REFERENCES inventory(id)
        );
        """
    )
    db.commit()

    count = query_one("SELECT COUNT(*) AS total FROM inventory")["total"]
    if count == 0:
        now = datetime.now().isoformat(timespec="minutes")
        seed_items = [
            ("Óleo motor 5W30", "Óleo e filtros", 42.00, 12, 3),
            ("Óleo motor 15W40", "Óleo e filtros", 38.00, 10, 3),
            ("Filtro de óleo", "Óleo e filtros", 28.00, 20, 5),
            ("Filtro de ar", "Óleo e filtros", 35.00, 12, 4),
            ("Filtro de combustível", "Óleo e filtros", 32.00, 10, 3),
            ("Pastilha de freio", "Freios", 120.00, 6, 2),
            ("Fluido de freio", "Freios", 26.00, 8, 2),
            ("Correia dentada", "Motor", 140.00, 4, 1),
            ("Vela de ignição", "Motor", 22.00, 24, 6),
            ("Bateria 60Ah", "Elétrica", 390.00, 3, 1),
            ("Lâmpada H4", "Elétrica", 25.00, 10, 2),
            ("Aditivo radiador", "Arrefecimento", 24.00, 12, 3),
        ]
        db.executemany(
            "INSERT INTO inventory (name, category, unit_price, qty, min_qty, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(name, cat, price, qty, min_qty, now) for name, cat, price, qty, min_qty in seed_items],
        )
        db.commit()


@app.context_processor
def inject_helpers() -> dict[str, Any]:
    return {
        "money": float_to_money,
        "br_date": br_date,
        "br_datetime": br_datetime,
        "today_iso": today_iso,
    }


@app.before_request
def ensure_db() -> None:
    init_db()


def order_totals(order_id: int) -> dict[str, float]:
    items_sum = query_one("SELECT COALESCE(SUM(total), 0) AS total FROM order_items WHERE order_id = ?", (order_id,))["total"]
    order = query_one("SELECT labor_value, discount FROM service_orders WHERE id = ?", (order_id,))
    labor = float(order["labor_value"] or 0) if order else 0.0
    discount = float(order["discount"] or 0) if order else 0.0
    total = max(0, labor + float(items_sum or 0) - discount)
    return {"items": float(items_sum or 0), "labor": labor, "discount": discount, "total": total}


def get_order_full(order_id: int) -> dict[str, Any] | None:
    order = query_one(
        """
        SELECT so.*, c.name AS client_name, c.phone, c.document, c.address,
               v.plate, v.brand, v.model, v.year, v.color, v.km AS vehicle_km
        FROM service_orders so
        JOIN clients c ON c.id = so.client_id
        JOIN vehicles v ON v.id = so.vehicle_id
        WHERE so.id = ?
        """,
        (order_id,),
    )
    if not order:
        return None
    items = query_all("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,))
    return {"order": order, "items": items, "totals": order_totals(order_id)}


def restore_items_to_stock(order_id: int) -> None:
    db = get_db()
    old_items = db.execute("SELECT inventory_id, qty FROM order_items WHERE order_id = ? AND inventory_id IS NOT NULL", (order_id,)).fetchall()
    for item in old_items:
        db.execute("UPDATE inventory SET qty = qty + ? WHERE id = ?", (float(item["qty"] or 0), item["inventory_id"]))
    db.commit()


def save_order_items(order_id: int, form: dict[str, list[str]]) -> None:
    db = get_db()
    inventory_ids = form.get("inventory_id", [])
    names = form.get("item_name", [])
    qtys = form.get("item_qty", [])
    prices = form.get("item_price", [])

    for idx in range(max(len(inventory_ids), len(names), len(qtys), len(prices))):
        inv_raw = inventory_ids[idx] if idx < len(inventory_ids) else ""
        name = (names[idx] if idx < len(names) else "").strip()
        qty = money_to_float(qtys[idx] if idx < len(qtys) else "1") or 1
        price = money_to_float(prices[idx] if idx < len(prices) else "0")
        inv_id = int(inv_raw) if inv_raw and inv_raw.isdigit() else None

        if inv_id:
            inv = db.execute("SELECT * FROM inventory WHERE id = ?", (inv_id,)).fetchone()
            if inv:
                name = name or inv["name"]
                price = price if price > 0 else float(inv["unit_price"] or 0)
        if not name and price == 0:
            continue
        total = round(qty * price, 2)
        db.execute(
            "INSERT INTO order_items (order_id, inventory_id, name, qty, unit_price, total) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, inv_id, name or "Item sem descrição", qty, price, total),
        )
        if inv_id:
            db.execute("UPDATE inventory SET qty = qty - ? WHERE id = ?", (qty, inv_id))
    db.commit()




@app.route("/service-worker.js")
def service_worker():
    response = make_response(send_from_directory(app.static_folder, "service-worker.js"))
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/"
    return response

@app.route("/")
def dashboard():
    stats = {
        "clients": query_one("SELECT COUNT(*) AS t FROM clients")["t"],
        "vehicles": query_one("SELECT COUNT(*) AS t FROM vehicles")["t"],
        "open_orders": query_one("SELECT COUNT(*) AS t FROM service_orders WHERE status = 'Aberta'")["t"],
        "low_stock": query_one("SELECT COUNT(*) AS t FROM inventory WHERE qty <= min_qty")["t"],
    }
    month = date.today().strftime("%Y-%m")
    orders_month = query_all("SELECT id FROM service_orders WHERE substr(order_date, 1, 7) = ?", (month,))
    monthly_total = sum(order_totals(int(row["id"]))["total"] for row in orders_month)
    recent_orders = query_all(
        """
        SELECT so.id, so.order_date, so.status, c.name AS client_name, v.plate, v.model
        FROM service_orders so
        JOIN clients c ON c.id = so.client_id
        JOIN vehicles v ON v.id = so.vehicle_id
        ORDER BY so.id DESC LIMIT 8
        """
    )
    return render_template("dashboard.html", stats=stats, monthly_total=monthly_total, recent_orders=recent_orders)


@app.route("/clientes")
def clients():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT c.*, COUNT(v.id) AS vehicles_count,
               GROUP_CONCAT(COALESCE(NULLIF(v.plate, ''), 'Sem placa') || ' - ' || COALESCE(v.model, ''), ' | ') AS vehicles
        FROM clients c
        LEFT JOIN vehicles v ON v.client_id = c.id
    """
    args: tuple[Any, ...] = ()
    if q:
        sql += " WHERE c.name LIKE ? OR c.phone LIKE ? OR c.document LIKE ? OR v.plate LIKE ? OR v.model LIKE ?"
        like = f"%{q}%"
        args = (like, like, like, like, like)
    sql += " GROUP BY c.id ORDER BY c.name"
    rows = query_all(sql, args)
    return render_template("clients.html", clients=rows, q=q)


@app.route("/clientes/novo", methods=["GET", "POST"])
def client_new():
    if request.method == "POST":
        now = datetime.now().isoformat(timespec="minutes")
        cur = execute(
            "INSERT INTO clients (name, phone, document, address, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                request.form.get("name", "").strip(),
                request.form.get("phone", "").strip(),
                request.form.get("document", "").strip(),
                request.form.get("address", "").strip(),
                now,
            ),
        )
        client_id = int(cur.lastrowid)
        execute(
            "INSERT INTO vehicles (client_id, plate, brand, model, year, color, km) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                client_id,
                request.form.get("plate", "").upper().strip(),
                request.form.get("brand", "").strip(),
                request.form.get("model", "").strip(),
                request.form.get("year", "").strip(),
                request.form.get("color", "").strip(),
                int(request.form.get("km") or 0),
            ),
        )
        flash("Cliente e veículo cadastrados com sucesso.", "success")
        return redirect(url_for("clients"))
    return render_template("client_form.html", client=None, vehicle=None)


@app.route("/clientes/<int:client_id>/editar", methods=["GET", "POST"])
def client_edit(client_id: int):
    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if not client:
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("clients"))
    vehicle = query_one("SELECT * FROM vehicles WHERE client_id = ? ORDER BY id LIMIT 1", (client_id,))
    if request.method == "POST":
        execute(
            "UPDATE clients SET name = ?, phone = ?, document = ?, address = ? WHERE id = ?",
            (
                request.form.get("name", "").strip(),
                request.form.get("phone", "").strip(),
                request.form.get("document", "").strip(),
                request.form.get("address", "").strip(),
                client_id,
            ),
        )
        if vehicle:
            execute(
                "UPDATE vehicles SET plate = ?, brand = ?, model = ?, year = ?, color = ?, km = ? WHERE id = ?",
                (
                    request.form.get("plate", "").upper().strip(),
                    request.form.get("brand", "").strip(),
                    request.form.get("model", "").strip(),
                    request.form.get("year", "").strip(),
                    request.form.get("color", "").strip(),
                    int(request.form.get("km") or 0),
                    vehicle["id"],
                ),
            )
        else:
            execute(
                "INSERT INTO vehicles (client_id, plate, brand, model, year, color, km) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    client_id,
                    request.form.get("plate", "").upper().strip(),
                    request.form.get("brand", "").strip(),
                    request.form.get("model", "").strip(),
                    request.form.get("year", "").strip(),
                    request.form.get("color", "").strip(),
                    int(request.form.get("km") or 0),
                ),
            )
        flash("Cadastro atualizado.", "success")
        return redirect(url_for("clients"))
    return render_template("client_form.html", client=client, vehicle=vehicle)


@app.route("/clientes/<int:client_id>/excluir", methods=["POST"])
def client_delete(client_id: int):
    execute("DELETE FROM clients WHERE id = ?", (client_id,))
    flash("Cliente excluído.", "success")
    return redirect(url_for("clients"))


@app.route("/os")
def orders():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    sql = """
        SELECT so.id, so.order_date, so.status, so.labor_value, so.discount,
               c.name AS client_name, v.plate, v.model
        FROM service_orders so
        JOIN clients c ON c.id = so.client_id
        JOIN vehicles v ON v.id = so.vehicle_id
        WHERE 1 = 1
    """
    args: list[Any] = []
    if q:
        sql += " AND (c.name LIKE ? OR v.plate LIKE ? OR v.model LIKE ? OR so.description LIKE ?)"
        like = f"%{q}%"
        args += [like, like, like, like]
    if status:
        sql += " AND so.status = ?"
        args.append(status)
    sql += " ORDER BY so.id DESC"
    rows = []
    for row in query_all(sql, tuple(args)):
        data = dict(row)
        data["total"] = order_totals(int(row["id"]))["total"]
        rows.append(data)
    return render_template("orders.html", orders=rows, q=q, status=status)


@app.route("/os/nova", methods=["GET", "POST"])
def order_new():
    clients_rows = query_all("SELECT * FROM clients ORDER BY name")
    vehicles = query_all(
        """
        SELECT v.*, c.name AS client_name
        FROM vehicles v JOIN clients c ON c.id = v.client_id
        ORDER BY c.name, v.plate
        """
    )
    inventory = query_all("SELECT * FROM inventory ORDER BY name")
    if not clients_rows:
        flash("Cadastre um cliente antes de abrir uma OS.", "error")
        return redirect(url_for("client_new"))
    if request.method == "POST":
        now = datetime.now().isoformat(timespec="minutes")
        client_id = int(request.form.get("client_id") or 0)
        vehicle_id = int(request.form.get("vehicle_id") or 0)
        cur = execute(
            """
            INSERT INTO service_orders
            (client_id, vehicle_id, order_date, status, km_atual, description, labor_value, discount, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                vehicle_id,
                request.form.get("order_date") or today_iso(),
                request.form.get("status") or "Aberta",
                int(request.form.get("km_atual") or 0),
                request.form.get("description", "").strip(),
                money_to_float(request.form.get("labor_value")),
                money_to_float(request.form.get("discount")),
                request.form.get("notes", "").strip(),
                now,
                now,
            ),
        )
        order_id = int(cur.lastrowid)
        save_order_items(order_id, request.form.to_dict(flat=False))
        flash("Ordem de serviço criada.", "success")
        return redirect(url_for("order_view", order_id=order_id))
    return render_template("order_form.html", order=None, items=[], clients=clients_rows, vehicles=vehicles, inventory=inventory)


@app.route("/os/<int:order_id>")
def order_view(order_id: int):
    data = get_order_full(order_id)
    if not data:
        flash("OS não encontrada.", "error")
        return redirect(url_for("orders"))
    return render_template("order_view.html", **data)


@app.route("/os/<int:order_id>/editar", methods=["GET", "POST"])
def order_edit(order_id: int):
    data = get_order_full(order_id)
    if not data:
        flash("OS não encontrada.", "error")
        return redirect(url_for("orders"))
    clients_rows = query_all("SELECT * FROM clients ORDER BY name")
    vehicles = query_all(
        """
        SELECT v.*, c.name AS client_name
        FROM vehicles v JOIN clients c ON c.id = v.client_id
        ORDER BY c.name, v.plate
        """
    )
    inventory = query_all("SELECT * FROM inventory ORDER BY name")
    if request.method == "POST":
        now = datetime.now().isoformat(timespec="minutes")
        execute(
            """
            UPDATE service_orders
            SET client_id = ?, vehicle_id = ?, order_date = ?, status = ?, km_atual = ?, description = ?,
                labor_value = ?, discount = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                int(request.form.get("client_id") or 0),
                int(request.form.get("vehicle_id") or 0),
                request.form.get("order_date") or today_iso(),
                request.form.get("status") or "Aberta",
                int(request.form.get("km_atual") or 0),
                request.form.get("description", "").strip(),
                money_to_float(request.form.get("labor_value")),
                money_to_float(request.form.get("discount")),
                request.form.get("notes", "").strip(),
                now,
                order_id,
            ),
        )
        restore_items_to_stock(order_id)
        execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        save_order_items(order_id, request.form.to_dict(flat=False))
        flash("OS atualizada.", "success")
        return redirect(url_for("order_view", order_id=order_id))
    return render_template("order_form.html", order=data["order"], items=data["items"], clients=clients_rows, vehicles=vehicles, inventory=inventory)


@app.route("/os/<int:order_id>/status", methods=["POST"])
def order_status(order_id: int):
    status = request.form.get("status") or "Aberta"
    execute("UPDATE service_orders SET status = ?, updated_at = ? WHERE id = ?", (status, datetime.now().isoformat(timespec="minutes"), order_id))
    flash("Status atualizado.", "success")
    return redirect(request.referrer or url_for("orders"))


@app.route("/os/<int:order_id>/excluir", methods=["POST"])
def order_delete(order_id: int):
    restore_items_to_stock(order_id)
    execute("DELETE FROM service_orders WHERE id = ?", (order_id,))
    flash("OS excluída e estoque restaurado.", "success")
    return redirect(url_for("orders"))


@app.route("/estoque", methods=["GET", "POST"])
def inventory():
    if request.method == "POST":
        execute(
            "INSERT INTO inventory (name, category, unit_price, qty, min_qty, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                request.form.get("name", "").strip(),
                request.form.get("category", "").strip(),
                money_to_float(request.form.get("unit_price")),
                money_to_float(request.form.get("qty")),
                money_to_float(request.form.get("min_qty")),
                datetime.now().isoformat(timespec="minutes"),
            ),
        )
        flash("Item cadastrado no estoque.", "success")
        return redirect(url_for("inventory"))
    q = request.args.get("q", "").strip()
    args: tuple[Any, ...] = ()
    sql = "SELECT * FROM inventory"
    if q:
        sql += " WHERE name LIKE ? OR category LIKE ?"
        like = f"%{q}%"
        args = (like, like)
    sql += " ORDER BY category, name"
    rows = query_all(sql, args)
    return render_template("inventory.html", inventory=rows, q=q)


@app.route("/estoque/<int:item_id>/editar", methods=["GET", "POST"])
def inventory_edit(item_id: int):
    item = query_one("SELECT * FROM inventory WHERE id = ?", (item_id,))
    if not item:
        flash("Item não encontrado.", "error")
        return redirect(url_for("inventory"))
    if request.method == "POST":
        execute(
            "UPDATE inventory SET name = ?, category = ?, unit_price = ?, qty = ?, min_qty = ? WHERE id = ?",
            (
                request.form.get("name", "").strip(),
                request.form.get("category", "").strip(),
                money_to_float(request.form.get("unit_price")),
                money_to_float(request.form.get("qty")),
                money_to_float(request.form.get("min_qty")),
                item_id,
            ),
        )
        flash("Item atualizado.", "success")
        return redirect(url_for("inventory"))
    return render_template("inventory_form.html", item=item)


@app.route("/estoque/<int:item_id>/excluir", methods=["POST"])
def inventory_delete(item_id: int):
    execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    flash("Item excluído.", "success")
    return redirect(url_for("inventory"))


@app.route("/relatorios")
def reports():
    start = request.args.get("start") or today_iso()
    end = request.args.get("end") or today_iso()
    status = request.args.get("status") or ""
    sql = """
        SELECT so.id, so.order_date, so.status, c.name AS client_name, v.plate, v.model, so.labor_value
        FROM service_orders so
        JOIN clients c ON c.id = so.client_id
        JOIN vehicles v ON v.id = so.vehicle_id
        WHERE so.order_date BETWEEN ? AND ?
    """
    args: list[Any] = [start, end]
    if status:
        sql += " AND so.status = ?"
        args.append(status)
    sql += " ORDER BY so.order_date DESC, so.id DESC"
    rows = []
    total_items = total_labor = total_discount = total = 0.0
    for row in query_all(sql, tuple(args)):
        totals = order_totals(int(row["id"]))
        data = dict(row)
        data.update(totals)
        rows.append(data)
        total_items += totals["items"]
        total_labor += totals["labor"]
        total_discount += totals["discount"]
        total += totals["total"]
    summary = {"items": total_items, "labor": total_labor, "discount": total_discount, "total": total, "count": len(rows)}
    return render_template("reports.html", rows=rows, summary=summary, start=start, end=end, status=status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG", "0") == "1")
