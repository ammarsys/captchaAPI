"""Routes for the API"""

import secrets
import datetime
import base64
from io import BytesIO
from urllib.parse import urljoin

from flask import send_file, render_template, jsonify, redirect, request

from .utils import cap_gen
from app import limiter, flask_app


def _id_generator(y: int) -> str:
    """
    Generates a captcha ID string of length 'y'.

    Args:
        y (int): The length of the captcha ID string to be generated.

    Returns:
        str: The captcha ID string of length 'y' generated by calling the 'choice' function on the given sequence of
            characters.

    """
    string = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKMNOPQRSTUVWXYZ"
    return "".join(secrets.choice(string) for _ in range(y))


def _b64_encrypt_id():
    """
    Encrypt given ID into base64.

    Decrypting this returns the captcha amount to date and the milisecond it was created
    """
    now = datetime.datetime.utcnow()
    time_now = now.strftime("%S")[-5:]

    return base64.b64encode(
        bytes(
            f"{flask_app.captcha_count}.{_id_generator(y=10)}.{time_now}",
            "utf-8",
        )
    ).decode()


@flask_app.route("/api/v5/cdn/<key>", methods=["GET"])
@limiter.limit("30/minute")
def get_img(key: str):
    """
    A Content Delivery Network (CDN) for serving captcha images.

    Args:
        key (str): The captcha identifier for which the image needs to be served.

    Returns:
        PIL.Image.Image: The captcha image corresponding to the given identifier.

    """
    try:
        if (
            flask_app.captcha_cdn[key]["cdn_accessed_number"]
            >= flask_app.captcha_cdn[key]["max_cdn_access"]
        ):
            del flask_app.captchas_solution[flask_app.captcha_cdn[key]["solution_id"]]
            del flask_app.captcha_cdn[key]

            return (
                jsonify(
                    {
                        "code": 418,
                        "type": "error",
                        "text": "captcha CDN accessed too many times, now expired & deleted",
                    }
                ),
                418,
            )

        flask_app.captcha_cdn[key]["cdn_accessed_number"] += 1

        if not flask_app.captcha_cdn[key]["image"]:
            pil_image = cap_gen(text=flask_app.captcha_cdn[key]["solution"])
            flask_app.captcha_cdn[key]["image"] = pil_image
        else:
            pil_image = flask_app.captcha_cdn[key]["image"]

        output = BytesIO()
        pil_image.convert("RGBA").save(output, format="PNG")
        output.seek(0, 0)

        return send_file(output, mimetype="image/png", as_attachment=False)

    except KeyError:
        return jsonify({"code": 400, "type": "error", "text": "cdn key not found"}), 400


@flask_app.route("/api/v5/captcha", methods=["POST"])
@limiter.limit("30/minute")
def api_captcha():
    """
    Endpoint for creating a dictionary key with the captcha ID and its related information. This route has an argument
    which indicates times the captcha image can be accessed before it is wiped from the dictionary.

    Two different types of cached dictionaries are stored,
        - captcha_cdn
        - captcha_solution

    Both have similar data but different access points (keys). This is so that the user cannot bruteforce the API
    directly. captcha_cdn key is shown (in CDN url) while captcha_solution is hidden.

    Returns:
        dict: A JSON dictionary containing the captcha ID and its related information.

    """
    data = request.get_json(silent=True) or {}
    cdn_access = data.get("maxCdnAccess", 5)
    solution_check = data.get("maxSolutionCheck", 5)

    if cdn_access >= 20 or cdn_access <= 0:
        return (
            jsonify(
                {
                    "type": "error",
                    "code": 400,
                    "text": "maxCdnAccess is over 20. default is 5 max is 20, min is 1",
                }
            ),
            400,
        )

    if solution_check >= 20 or solution_check <= 0:
        return (
            jsonify(
                {
                    "type": "error",
                    "code": 400,
                    "text": "maxSolutionCheck is over 20. default is 5 max is 20, min is 1",
                }
            ),
            400,
        )

    solution_id = _b64_encrypt_id()
    solution = _id_generator(y=secrets.choice((4, 5)))
    flask_app.captchas_solution[solution_id] = {
        "solution": solution,
        "max_solution_check": solution_check,
        "solution_checked": 0,
    }

    delta = datetime.timedelta(minutes=5)
    now = datetime.datetime.utcnow()
    cdn_id = _b64_encrypt_id()
    flask_app.captcha_cdn[cdn_id] = {
        "solution": solution,
        "image": None,
        "time": now + delta,
        "cdn_accessed_number": 0,
        "max_cdn_access": cdn_access,
        "solution_id": solution_id,
    }
    flask_app.captcha_count += 1

    return jsonify(
        {
            "cdn_url": urljoin(request.host_url, f"/api/v5/cdn/{cdn_id}"),
            "solution_check_url": urljoin(
                request.host_url, f"/api/v5/check/{solution_id}"
            ),
            "solution_id": solution_id,
            "cdn_id": cdn_id,
        }
    )


@flask_app.route("/api/v5/check/<solution_id>", methods=["POST"])
@limiter.limit("10/minute")
def check_solution(solution_id: str):
    if solution_id not in flask_app.captchas_solution:
        return {"type": "error", "code": 400, "text": "solution_id not found"}, 400

    if (
        flask_app.captchas_solution[solution_id]["solution_checked"]
        >= flask_app.captchas_solution[solution_id]["max_solution_check"]
    ):
        # We do not delete it from flask_app.captcha_cdn; let TTL cache GC handle it
        del flask_app.captchas_solution[solution_id]

        return (
            jsonify(
                {
                    "code": 418,
                    "type": "error",
                    "text": "this route has been accessed too many times. records now expired & deleted",
                }
            ),
            418,
        )

    flask_app.captchas_solution[solution_id]["solution_checked"] += 1

    data = {"case_sensitive_correct": False, "case_insensitive_correct": False}

    rq_data = request.get_json()
    attempt = rq_data.get("attempt")
    captcha_data = flask_app.captchas_solution.get(solution_id)

    if not attempt:
        return {
            "type": "error",
            "code": 400,
            "text": "attempt not found in HTTP json",
        }, 400

    if attempt == captcha_data["solution"]:
        data["case_sensitive_correct"] = True

    if attempt.lower() == captcha_data["solution"].lower():  # type: ignore
        data["case_insensitive_correct"] = True

    return jsonify(data)


@flask_app.route("/examples", methods=["GET"])
def examples():
    """API examples endpoint"""
    return render_template("examples.html")


@flask_app.route("/", methods=["GET"])
def home():
    """API home"""
    return render_template("index.html")


@flask_app.errorhandler(404)
def not_found(_):
    """404 error handling"""
    return redirect("/")


@flask_app.errorhandler(429)
def ratelimited(_):
    """429 error handling"""
    return jsonify({"type": "ratelimited", "code": 429, "text": "too fast"}), 429


@flask_app.errorhandler(405)
def method_not_allowed(_):
    """405 Method Not Allowed"""
    return (
        jsonify({"type": "not allowed", "code": 405, "text": "method not allowed"}),
        405,
    )
