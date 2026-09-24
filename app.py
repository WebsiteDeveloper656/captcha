from flask import (
    Flask,
    request,
    jsonify,
    send_file,
    render_template,
    redirect,
    url_for,
    session
)

from flask_cors import CORS
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from werkzeug.middleware.proxy_fix import ProxyFix

from PIL import Image, ImageDraw, ImageFont

import sqlite3
import secrets
import io
import time
import random
import os
import razorpay


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1
)

# =========================================================
# SECRET KEY
# =========================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-secret-change-this"
)

# =========================================================
# CORS
# =========================================================

CORS(app)


# =========================================================
# RAZORPAY CONFIGURATION
# =========================================================

RAZORPAY_KEY_ID = os.environ.get(
    "RAZORPAY_KEY_ID"
)

RAZORPAY_KEY_SECRET = os.environ.get(
    "RAZORPAY_KEY_SECRET"
)

RAZORPAY_WEBHOOK_SECRET = os.environ.get(
    "RAZORPAY_WEBHOOK_SECRET"
)


razorpay_client = None


if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:

    razorpay_client = razorpay.Client(
        auth=(
            RAZORPAY_KEY_ID,
            RAZORPAY_KEY_SECRET
        )
    )

    print("Razorpay configured successfully.")

else:

    print(
        "WARNING: Razorpay keys are not configured."
    )


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATABASE = os.path.join(
    BASE_DIR,
    "database.db"
)


# =========================================================
# SETTINGS
# =========================================================

CAPTCHA_EXPIRY = 120


# =========================================================
# PLANS
# =========================================================

PLANS = {

    "free": {
        "price": 0
    },

    "basic": {
        "price": 299
    },

    "pro": {
        "price": 999
    }

}


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(
        DATABASE,
        timeout=10
    )

    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    return conn


def init_db():

    conn = get_db()

    # =====================================================
    # USERS
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            api_key TEXT UNIQUE NOT NULL,

            plan TEXT NOT NULL DEFAULT 'free',

            usage INTEGER NOT NULL DEFAULT 0,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # =====================================================
    # CAPTCHAS
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS captchas (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            captcha_id TEXT UNIQUE NOT NULL,

            user_id INTEGER NOT NULL,

            captcha_text TEXT NOT NULL,

            captcha_hash TEXT NOT NULL,

            created_at REAL NOT NULL,

            expires_at REAL NOT NULL,

            used INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY (user_id)
                REFERENCES users(id)

        )
    """)

    # =====================================================
    # PAYMENTS
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            plan TEXT NOT NULL,

            amount INTEGER NOT NULL,

            razorpay_order_id TEXT UNIQUE NOT NULL,

            razorpay_payment_id TEXT,

            status TEXT NOT NULL DEFAULT 'created',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)

        )
    """)

    conn.commit()
    conn.close()


# Initialize database
init_db()


# =========================================================
# CAPTCHA TEXT
# =========================================================

def generate_captcha_text(length=6):

    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    return "".join(
        secrets.choice(chars)
        for _ in range(length)
    )


# =========================================================
# CAPTCHA IMAGE
# =========================================================

def get_captcha_font(size=36):

    font_paths = [

        # Linux / Render
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",

        # Project folder
        os.path.join(
            BASE_DIR,
            "DejaVuSans-Bold.ttf"
        ),

        # Windows
        "arial.ttf"

    ]

    for path in font_paths:

        try:

            return ImageFont.truetype(
                path,
                size
            )

        except Exception:
            pass

    return ImageFont.load_default()


def create_captcha_image(text):

    width = 200
    height = 70

    img = Image.new(
        "RGB",
        (width, height),
        (240, 245, 250)
    )

    pixels = img.load()

    # =====================================================
    # BACKGROUND NOISE
    # =====================================================

    for x in range(width):

        for y in range(height):

            noise = random.randint(
                -30,
                30
            )

            r, g, b = pixels[x, y]

            pixels[x, y] = (

                min(
                    255,
                    max(0, r + noise)
                ),

                min(
                    255,
                    max(0, g + noise)
                ),

                min(
                    255,
                    max(0, b + noise)
                )

            )

    draw = ImageDraw.Draw(img)

    # =====================================================
    # NOISE LINES
    # =====================================================

    for _ in range(5):

        draw.line(

            [

                (
                    random.randint(0, width),
                    random.randint(0, height)
                ),

                (
                    random.randint(0, width),
                    random.randint(0, height)
                )

            ],

            fill=(

                random.randint(0, 150),
                random.randint(0, 150),
                random.randint(0, 150)

            ),

            width=2

        )

    # =====================================================
    # CHARACTERS
    # =====================================================

    char_width = width // len(text)

    for i, char in enumerate(text):

        font_size = 36

        font = get_captcha_font(
            font_size
        )

        x = (
            i * char_width
            + random.randint(5, 10)
        )

        y = random.randint(
            10,
            18
        )

        color = (

            random.randint(0, 80),
            random.randint(0, 80),
            random.randint(0, 80)

        )

        char_img = Image.new(

            "RGBA",

            (
                font_size + 20,
                font_size + 20
            ),

            (0, 0, 0, 0)

        )

        char_draw = ImageDraw.Draw(
            char_img
        )

        char_draw.text(

            (5, 0),

            char,

            font=font,

            fill=color

        )

        char_img = char_img.rotate(

            random.randint(-25, 25),

            expand=True

        )

        img.paste(

            char_img,

            (x, y),

            char_img

        )

    return img


# =========================================================
# CURRENT SESSION USER
# =========================================================

def get_current_user():

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return user


# =========================================================
# API USER
# =========================================================

def get_api_user():

    api_key = request.headers.get(
        "X-API-Key"
    )

    if not api_key:
        return None

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE api_key = ?
        """,
        (api_key,)
    ).fetchone()

    conn.close()

    return user


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    if session.get("user_id"):

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("register")
    )


# =========================================================
# REGISTER PAGE
# =========================================================

@app.route("/register")
def register():

    if session.get("user_id"):

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# REGISTER USER
# =========================================================

@app.route(
    "/register",
    methods=["POST"]
)
def register_user():

    name = request.form.get(
        "name",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    if not name or not email or not password:

        return render_template(
            "register.html",
            error="All fields are required"
        )

    if len(password) < 6:

        return render_template(
            "register.html",
            error=(
                "Password must be at least "
                "6 characters"
            )
        )

    password_hash = generate_password_hash(
        password
    )

    api_key = secrets.token_urlsafe(
        32
    )

    conn = get_db()

    try:

        cursor = conn.execute(

            """
            INSERT INTO users
            (
                name,
                email,
                password,
                api_key,
                plan,
                usage
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,

            (
                name,
                email,
                password_hash,
                api_key,
                "free",
                0
            )

        )

        conn.commit()

        user_id = cursor.lastrowid

    except sqlite3.IntegrityError:

        conn.close()

        return render_template(
            "register.html",
            error="Email already registered"
        )

    conn.close()

    session["user_id"] = user_id

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# LOGIN PAGE
# =========================================================

@app.route("/login")
def login():

    if session.get("user_id"):

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGIN USER
# =========================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login_user():

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    conn.close()

    if not user:

        return render_template(
            "login.html",
            error="Invalid email or password"
        )

    if not check_password_hash(
        user["password"],
        password
    ):

        return render_template(
            "login.html",
            error="Invalid email or password"
        )

    session["user_id"] = user["id"]

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    user = get_current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    plan_name = user["plan"]

    plan_data = PLANS.get(
        plan_name,
        PLANS["free"]
    )

    # Current code uses usage as displayed remaining value.
    remaining = max(
        0,
        int(user["usage"])
    )

    conn = get_db()

    payments = conn.execute("""

        SELECT
            plan,
            amount,
            razorpay_order_id,
            razorpay_payment_id,
            status,
            created_at

        FROM payments

        WHERE user_id = ?

        ORDER BY id DESC

    """, (
        user["id"],
    )).fetchall()

    conn.close()

    return render_template(

        "dashboard.html",

        user=user,

        plan=plan_name,

        price=plan_data["price"],

        remaining=remaining,

        payments=payments

    )


# =========================================================
# REGENERATE API KEY
# =========================================================

@app.route(
    "/api-key/regenerate",
    methods=["POST"]
)
def regenerate_api_key():

    user = get_current_user()

    if not user:

        return jsonify({

            "success": False,

            "error":
                "Login required"

        }), 401

    new_key = secrets.token_urlsafe(
        32
    )

    conn = get_db()

    try:

        conn.execute(

            """
            UPDATE users
            SET api_key = ?
            WHERE id = ?
            """,

            (
                new_key,
                user["id"]
            )

        )

        conn.commit()

    except Exception as e:

        conn.rollback()
        conn.close()

        print(
            "API key error:",
            e
        )

        return jsonify({

            "success": False,

            "error":
                "Could not regenerate API key"

        }), 500

    conn.close()

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# CREATE PAYMENT ORDER
# =========================================================

@app.route(
    "/payment/create-order",
    methods=["POST"]
)
def create_payment_order():

    user = get_current_user()

    if not user:

        return jsonify({

            "success": False,

            "error":
                "Login required"

        }), 401

    if razorpay_client is None:

        return jsonify({

            "success": False,

            "error":
                "Razorpay is not configured. "
                "Check RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET."

        }), 500

    data = request.get_json(
        silent=True
    ) or {}

    plan_name = data.get(
        "plan"
    )

    # =====================================================
    # PLAN VALIDATION
    # =====================================================

    if plan_name not in (
        "basic",
        "pro"
    ):

        return jsonify({

            "success": False,

            "error":
                "Invalid plan"

        }), 400

    plan = PLANS[plan_name]

    # =====================================================
    # AMOUNT
    # =====================================================

    amount = (
        plan["price"] * 100
    )

    receipt = (
        "user_"
        + str(user["id"])
        + "_"
        + secrets.token_hex(6)
    )

    # =====================================================
    # RAZORPAY ORDER
    # =====================================================

    try:

        order = razorpay_client.order.create({

            "amount": amount,

            "currency": "INR",

            "receipt": receipt

        })

    except Exception as e:

        print(
            "Razorpay order creation error:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "error":
                "Could not create Razorpay order"

        }), 500

    # =====================================================
    # SAVE PAYMENT
    # =====================================================

    conn = get_db()

    try:

        conn.execute("""

            INSERT INTO payments
            (
                user_id,
                plan,
                amount,
                razorpay_order_id,
                status
            )

            VALUES (?, ?, ?, ?, ?)

        """, (

            user["id"],

            plan_name,

            amount,

            order["id"],

            "created"

        ))

        conn.commit()

    except Exception as e:

        conn.rollback()
        conn.close()

        print(
            "Payment database error:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "error":
                "Could not save payment order"

        }), 500

    conn.close()

    return jsonify({

        "success": True,

        "order_id":
            order["id"],

        "amount":
            amount,

        "currency":
            "INR",

        "plan":
            plan_name,

        "key_id":
            RAZORPAY_KEY_ID

    })


# =========================================================
# VERIFY PAYMENT
# =========================================================

@app.route(
    "/payment/verify",
    methods=["POST"]
)
def verify_payment():

    user = get_current_user()

    if not user:

        return jsonify({

            "success": False,

            "error":
                "Login required"

        }), 401

    if razorpay_client is None:

        return jsonify({

            "success": False,

            "error":
                "Razorpay is not configured"

        }), 500

    data = request.get_json(
        silent=True
    ) or {}

    razorpay_order_id = data.get(
        "razorpay_order_id"
    )

    razorpay_payment_id = data.get(
        "razorpay_payment_id"
    )

    razorpay_signature = data.get(
        "razorpay_signature"
    )

    if not razorpay_order_id:

        return jsonify({

            "success": False,

            "error":
                "razorpay_order_id is required"

        }), 400

    if not razorpay_payment_id:

        return jsonify({

            "success": False,

            "error":
                "razorpay_payment_id is required"

        }), 400

    if not razorpay_signature:

        return jsonify({

            "success": False,

            "error":
                "razorpay_signature is required"

        }), 400

    conn = get_db()

    try:

        # =================================================
        # FIND PAYMENT
        # =================================================

        payment = conn.execute("""

            SELECT *

            FROM payments

            WHERE razorpay_order_id = ?

            AND user_id = ?

        """, (

            razorpay_order_id,

            user["id"]

        )).fetchone()

        if not payment:

            return jsonify({

                "success": False,

                "error":
                    "Payment order not found"

            }), 404

        # =================================================
        # ALREADY PAID
        # =================================================

        if payment["status"] == "paid":

            return jsonify({

                "success": True,

                "message":
                    "Payment already verified",

                "plan":
                    payment["plan"]

            }), 200

        # =================================================
        # VERIFY RAZORPAY SIGNATURE
        # =================================================

        try:

            razorpay_client.utility.verify_payment_signature({

                "razorpay_order_id":
                    razorpay_order_id,

                "razorpay_payment_id":
                    razorpay_payment_id,

                "razorpay_signature":
                    razorpay_signature

            })

        except Exception as e:

            print(
                "Razorpay signature error:",
                repr(e)
            )

            return jsonify({

                "success": False,

                "error":
                    "Payment verification failed"

            }), 400

        # =================================================
        # PLAN
        # =================================================

        plan_name = payment["plan"]

        if plan_name not in PLANS:

            return jsonify({

                "success": False,

                "error":
                    "Invalid plan"

            }), 400

        # =================================================
        # AMOUNT CHECK
        # =================================================

        expected_amount = (
            PLANS[plan_name]["price"] * 100
        )

        if payment["amount"] != expected_amount:

            return jsonify({

                "success": False,

                "error":
                    "Payment amount mismatch"

            }), 400

        # =================================================
        # UPDATE PAYMENT
        # =================================================

        cursor = conn.execute("""

            UPDATE payments

            SET
                razorpay_payment_id = ?,
                status = 'paid'

            WHERE razorpay_order_id = ?

            AND user_id = ?

            AND status = 'created'

        """, (

            razorpay_payment_id,

            razorpay_order_id,

            user["id"]

        ))

        # If another request already processed it
        if cursor.rowcount != 1:

            conn.rollback()

            return jsonify({

                "success": False,

                "error":
                    "Payment was already processed"

            }), 409

        # =================================================
        # UPDATE USER PLAN
        # =================================================

        conn.execute("""

            UPDATE users

            SET
                plan = ?,
                usage = 0

            WHERE id = ?

        """, (

            plan_name,

            user["id"]

        ))

        conn.commit()

    except Exception as e:

        conn.rollback()

        print(
            "Payment verification database error:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "error":
                "Could not verify payment"

        }), 500

    finally:

        conn.close()

    return jsonify({

        "success": True,

        "message":
            "Payment verified successfully",

        "plan":
            plan_name

    })


# =========================================================
# RAZORPAY WEBHOOK
# =========================================================

@app.route(
    "/payment/webhook",
    methods=["POST"]
)
def payment_webhook():

    webhook_body = request.get_data(
        as_text=True
    )

    webhook_signature = request.headers.get(
        "X-Razorpay-Signature"
    )

    # =====================================================
    # BASIC CHECKS
    # =====================================================

    if not webhook_signature:

        return jsonify({

            "success": False,

            "error":
                "Webhook signature missing"

        }), 400

    if not RAZORPAY_WEBHOOK_SECRET:

        print(
            "RAZORPAY_WEBHOOK_SECRET "
            "is not configured"
        )

        return jsonify({

            "success": False,

            "error":
                "Webhook not configured"

        }), 500

    if razorpay_client is None:

        return jsonify({

            "success": False,

            "error":
                "Razorpay is not configured"

        }), 500

    # =====================================================
    # VERIFY WEBHOOK SIGNATURE
    # =====================================================

    try:

        razorpay_client.utility.verify_webhook_signature(

            webhook_body,

            webhook_signature,

            RAZORPAY_WEBHOOK_SECRET

        )

    except Exception as e:

        print(
            "Webhook verification error:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "error":
                "Invalid webhook signature"

        }), 400

    # =====================================================
    # JSON
    # =====================================================

    payload = request.get_json(
        silent=True
    )

    if not payload:

        return jsonify({

            "success": False,

            "error":
                "Invalid JSON"

        }), 400

    event = payload.get(
        "event"
    )

    print(
        "Razorpay webhook event:",
        event
    )

    # =====================================================
    # PAYMENT CAPTURED
    # =====================================================

    if event == "payment.captured":

        payment_entity = (

            payload
            .get("payload", {})
            .get("payment", {})
            .get("entity", {})

        )

        razorpay_payment_id = (
            payment_entity.get("id")
        )

        razorpay_order_id = (
            payment_entity.get("order_id")
        )

        webhook_amount = (
            payment_entity.get("amount")
        )

        if not razorpay_order_id:

            return jsonify({

                "success": False,

                "error":
                    "Order ID missing"

            }), 400

        conn = get_db()

        try:

            # =================================================
            # FIND PAYMENT
            # =================================================

            payment = conn.execute("""

                SELECT *

                FROM payments

                WHERE razorpay_order_id = ?

            """, (

                razorpay_order_id,

            )).fetchone()

            if not payment:

                print(
                    "Webhook order not found:",
                    razorpay_order_id
                )

                return jsonify({

                    "success": True,

                    "message":
                        "Order not found"

                }), 200

            # =================================================
            # ALREADY PAID
            # =================================================

            if payment["status"] == "paid":

                return jsonify({

                    "success": True,

                    "message":
                        "Payment already processed"

                }), 200

            # =================================================
            # PLAN
            # =================================================

            plan_name = payment["plan"]

            if plan_name not in PLANS:

                return jsonify({

                    "success": False,

                    "error":
                        "Invalid plan"

                }), 400

            # =================================================
            # AMOUNT
            # =================================================

            expected_amount = (
                PLANS[plan_name]["price"] * 100
            )

            if webhook_amount != expected_amount:

                print(
                    "Webhook amount mismatch:",
                    webhook_amount,
                    expected_amount
                )

                return jsonify({

                    "success": False,

                    "error":
                        "Payment amount mismatch"

                }), 400

            # =================================================
            # UPDATE PAYMENT
            # =================================================

            cursor = conn.execute("""

                UPDATE payments

                SET
                    razorpay_payment_id = ?,
                    status = 'paid'

                WHERE razorpay_order_id = ?

                AND status = 'created'

            """, (

                razorpay_payment_id,

                razorpay_order_id

            ))

            if cursor.rowcount != 1:

                conn.rollback()

                return jsonify({

                    "success": True,

                    "message":
                        "Payment already processed"

                }), 200

            # =================================================
            # UPDATE USER
            # =================================================

            conn.execute("""

                UPDATE users

                SET
                    plan = ?,
                    usage = 0

                WHERE id = ?

            """, (

                plan_name,

                payment["user_id"]

            ))

            conn.commit()

        except Exception as e:

            conn.rollback()

            print(
                "Webhook database error:",
                repr(e)
            )

            return jsonify({

                "success": False,

                "error":
                    "Webhook processing failed"

            }), 500

        finally:

            conn.close()

        print(

            "Payment processed successfully:",

            razorpay_order_id,

            plan_name

        )

    # =====================================================
    # OTHER EVENTS
    # =====================================================

    return jsonify({

        "success": True

    }), 200


# =========================================================
# DEMO
# =========================================================

@app.route("/demo")
def demo():

    user = get_current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    return render_template(

        "demo.html",

        api_key=user["api_key"]

    )


# =========================================================
# CREATE CAPTCHA
# =========================================================

@app.route(
    "/captcha/create",
    methods=["POST"]
)
def create_captcha():

    user = get_api_user()

    if not user:

        return jsonify({

            "success": False,

            "error":
                "Invalid API key"

        }), 401

    captcha_id = secrets.token_urlsafe(
        16
    )

    captcha_text = generate_captcha_text()

    created_at = time.time()

    expires_at = (
        created_at
        + CAPTCHA_EXPIRY
    )

    captcha_hash = generate_password_hash(
        captcha_text
    )

    conn = get_db()

    try:

        conn.execute("""

            INSERT INTO captchas

            (
                captcha_id,
                user_id,
                captcha_text,
                captcha_hash,
                created_at,
                expires_at,
                used
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

        """, (

            captcha_id,

            user["id"],

            captcha_text,

            captcha_hash,

            created_at,

            expires_at,

            0

        ))

        # =================================================
        # USAGE
        # =================================================

        conn.execute("""

            UPDATE users

            SET usage = usage + 1

            WHERE id = ?

        """, (

            user["id"],

        ))

        conn.commit()

    except Exception as e:

        conn.rollback()
        conn.close()

        print(
            "CAPTCHA creation error:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "error":
                "Could not create CAPTCHA"

        }), 500

    conn.close()

    # =====================================================
    # IMAGE URL
    # =====================================================

    image_url = url_for(

        "captcha_image",

        captcha_id=captcha_id,

        _external=True

    )

    return jsonify({

        "success": True,

        "captcha_id":
            captcha_id,

        "image_url":
            image_url,

        "expires_in":
            CAPTCHA_EXPIRY

    })


# =========================================================
# CAPTCHA IMAGE
# =========================================================

@app.route(
    "/captcha/image/<captcha_id>"
)
def captcha_image(captcha_id):

    user = get_api_user()

    if not user:

        return jsonify({

            "success": False,

            "error":
                "Invalid API key"

        }), 401

    conn = get_db()

    captcha = conn.execute("""

        SELECT *

        FROM captchas

        WHERE captcha_id = ?

    """, (

        captcha_id,

    )).fetchone()

    if not captcha:

        conn.close()

        return jsonify({

            "success": False,

            "error":
                "CAPTCHA not found"

        }), 404

    # =====================================================
    # OWNERSHIP
    # =====================================================

    if captcha["user_id"] != user["id"]:

        conn.close()

        return jsonify({

            "success": False,

            "error":
                "Unauthorized CAPTCHA"

        }), 403

    # =====================================================
    # EXPIRY
    # =====================================================

    if time.time() > captcha["expires_at"]:

        conn.close()

        return jsonify({

            "success": False,

            "error":
                "CAPTCHA expired"

        }), 410

    # =====================================================
    # USED
    # =====================================================

    if captcha["used"]:

        conn.close()

        return jsonify({

            "success": False,

            "error":
                "CAPTCHA already used"

        }), 410

    # =====================================================
    # CREATE IMAGE
    # =====================================================

    img = create_captcha_image(

        captcha["captcha_text"]

    )

    image_bytes = io.BytesIO()

    img.save(

        image_bytes,

        format="PNG"

    )

    image_bytes.seek(0)

    conn.close()

    return send_file(

        image_bytes,

        mimetype="image/png"

    )


# =========================================================
# VERIFY CAPTCHA
# =========================================================

@app.route(
    "/captcha/verify",
    methods=["POST"]
)
def verify_captcha():

    user = get_api_user()

    if not user:

        return jsonify({

            "success": False,

            "error":
                "Invalid API key"

        }), 401

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({

            "success": False,

            "error":
                "JSON body required"

        }), 400

    captcha_id = data.get(
        "captcha_id"
    )

    answer = data.get(
        "answer",
        ""
    )

    if not captcha_id:

        return jsonify({

            "success": False,

            "error":
                "captcha_id is required"

        }), 400

    if not isinstance(
        answer,
        str
    ):

        return jsonify({

            "success": False,

            "error":
                "answer must be a string"

        }), 400

    answer = answer.strip().upper()

    if not answer:

        return jsonify({

            "success": False,

            "error":
                "answer is required"

        }), 400

    conn = get_db()

    try:

        captcha = conn.execute("""

            SELECT *

            FROM captchas

            WHERE captcha_id = ?

            AND user_id = ?

        """, (

            captcha_id,

            user["id"]

        )).fetchone()

        # =================================================
        # NOT FOUND
        # =================================================

        if not captcha:

            return jsonify({

                "success": False,

                "verified": False,

                "error":
                    "CAPTCHA not found"

            }), 404

        # =================================================
        # EXPIRED
        # =================================================

        if time.time() > captcha["expires_at"]:

            return jsonify({

                "success": False,

                "verified": False,

                "error":
                    "CAPTCHA expired"

            }), 410

        # =================================================
        # USED
        # =================================================

        if captcha["used"]:

            return jsonify({

                "success": False,

                "verified": False,

                "error":
                    "CAPTCHA already used"

            }), 410

        # =================================================
        # CHECK ANSWER
        # =================================================

        correct = check_password_hash(

            captcha["captcha_hash"],

            answer

        )

        if not correct:

            return jsonify({

                "success": True,

                "verified": False,

                "message":
                    "Incorrect CAPTCHA"

            }), 200

        # =================================================
        # MARK CAPTCHA USED
        # =================================================

        cursor = conn.execute("""

            UPDATE captchas

            SET used = 1

            WHERE captcha_id = ?

            AND user_id = ?

            AND used = 0

        """, (

            captcha_id,

            user["id"]

        ))

        if cursor.rowcount != 1:

            conn.rollback()

            return jsonify({

                "success": False,

                "verified": False,

                "error":
                    "CAPTCHA already used"

            }), 410

        conn.commit()

        return jsonify({

            "success": True,

            "verified": True,

            "message":
                "CAPTCHA verified successfully"

        }), 200

    except Exception as e:

        conn.rollback()

        print(
            "CAPTCHA verification error:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "error":
                "Could not verify CAPTCHA"

        }), 500

    finally:

        conn.close()


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(

        host="0.0.0.0",

        port=port,

        debug=False

    )
