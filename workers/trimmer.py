"""
Скрипт-обрезчик: превращает грязный Reddit JSON в чистые данные.
Единственное место где режутся данные перед передачей в Claude.
"""

from workers.helpers import load_config


def trim_posts(raw_children, config=None):
    """
    Принимает data["children"] из Reddit JSON.
    Возвращает список чистых постов.
    """
    if config is None:
        config = load_config()

    body_max = config.get("body_max_chars", 300)
    min_upvotes = config.get("min_upvotes", 50)
    result = []

    for child in raw_children:
        d = child.get("data", {})

        if d.get("promoted"):
            continue
        if d.get("is_reddit_media_domain"):
            continue
        if d.get("ups", 0) < min_upvotes:
            continue

        body = d.get("selftext", "") or ""

        result.append({
            "reddit_id": d.get("id", ""),
            "title": d.get("title", ""),
            "body": body[:body_max],
            "upvotes": d.get("ups", 0),
            "num_comments": d.get("num_comments", 0),
            "url": f"https://reddit.com{d.get('permalink', '')}",
            "flair": d.get("link_flair_text") or "",
            "subreddit": d.get("subreddit", ""),
        })

    return result


def trim_comments(raw_json, config=None):
    """
    Принимает полный JSON ответа /comments/{id}.json.
    Возвращает список чистых комментариев, отсортированных по апвоутам.
    """
    if config is None:
        config = load_config()

    comment_max = config.get("comment_max_chars", 200)
    top_n = config.get("comments_top_n", 10)
    comments = []

    if not isinstance(raw_json, list) or len(raw_json) < 2:
        return []

    children = raw_json[1].get("data", {}).get("children", [])

    for item in children:
        if item.get("kind") != "t1":
            continue
        d = item.get("data", {})
        body = d.get("body", "")

        if not body or body in ("[deleted]", "[removed]"):
            continue

        comments.append({
            "text": body[:comment_max],
            "ups": d.get("score", 0),
            "is_op": d.get("is_submitter", False),
        })

    # Сортируем по апвоутам, берём топ-N
    comments.sort(key=lambda c: c["ups"], reverse=True)
    return comments[:top_n]
