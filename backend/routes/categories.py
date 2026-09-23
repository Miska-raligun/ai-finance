"""分类管理路由"""
from flask import Blueprint, request, jsonify, g
from db import get_db
from auth import login_required
from constants import CATEGORY_EXPENSE, CATEGORY_INCOME

categories_bp = Blueprint('categories', __name__)


@categories_bp.route("/api/categories", methods=["GET"])
@login_required
def get_categories():
    db = get_db()
    category_type = request.args.get("type")

    type_map = {
        "income": CATEGORY_INCOME,
        "expense": CATEGORY_EXPENSE,
    }

    if category_type in type_map:
        cursor = db.execute(
            "SELECT * FROM categories WHERE type = ? AND user_id = ? ORDER BY name ASC",
            (type_map[category_type], g.user_id)
        )
    else:
        cursor = db.execute(
            "SELECT * FROM categories WHERE user_id = ? ORDER BY name ASC",
            (g.user_id,)
        )

    results = [dict(row) for row in cursor.fetchall()]
    if not isinstance(results, list):
        return jsonify([])
    return jsonify(results)


@categories_bp.route("/api/categories", methods=["POST"])
@login_required
def add_category_manual():
    data = request.get_json()
    name = data.get("name", "").strip()
    category_type = data.get("type", CATEGORY_EXPENSE).strip()

    if not name:
        return jsonify({"error": "缺少分类名称"}), 400
    if category_type not in (CATEGORY_EXPENSE, CATEGORY_INCOME):
        return jsonify({"error": "分类类型必须是「支出」或「收入」"}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (g.user_id, name, category_type)
        )
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@categories_bp.route("/api/categories/<name>", methods=["DELETE"])
@login_required
def delete_category_manual(name):
    db = get_db()

    row = db.execute(
        "SELECT type FROM categories WHERE name = ? AND user_id = ?",
        (name, g.user_id)
    ).fetchone()
    if not row:
        return jsonify({"error": f"分类「{name}」不存在"}), 404

    category_type = row["type"]

    if category_type == CATEGORY_EXPENSE:
        db.execute("DELETE FROM records WHERE category = ? AND user_id = ?", (name, g.user_id))
        db.execute("DELETE FROM budgets WHERE category = ? AND user_id = ?", (name, g.user_id))
    elif category_type == CATEGORY_INCOME:
        db.execute("DELETE FROM income WHERE category = ? AND user_id = ?", (name, g.user_id))

    db.execute("DELETE FROM categories WHERE name = ? AND user_id = ?", (name, g.user_id))
    db.commit()

    return jsonify({"success": True})
