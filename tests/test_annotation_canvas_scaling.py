from app.services.media_service import _normalize_canvas_json


def test_normalize_canvas_json_scales_path_to_target_size():
    canvas_json = {
        "__meta": {
            "canvasWidth": 640,
            "canvasHeight": 360,
            "sourceWidth": 1280,
            "sourceHeight": 720,
        },
        "objects": [
            {
                "type": "path",
                "stroke": "#ef4444",
                "strokeWidth": 3,
                "path": [
                    ["M", 500, 150],
                    ["Q", 560, 160, 600, 200],
                ],
            }
        ],
    }

    normalized = _normalize_canvas_json(canvas_json, (1280, 720))

    assert normalized["objects"][0]["path"][0] == ["M", 1000.0, 300.0]
    assert normalized["objects"][0]["path"][1] == ["Q", 1120.0, 320.0, 1200.0, 400.0]


def test_normalize_canvas_json_scales_geometry_fields():
    canvas_json = {
        "__meta": {
            "canvasWidth": 400,
            "canvasHeight": 800,
        },
        "objects": [
            {
                "type": "rect",
                "left": 50,
                "top": 120,
                "width": 80,
                "height": 160,
                "strokeWidth": 4,
            }
        ],
    }

    normalized = _normalize_canvas_json(canvas_json, (800, 1600))
    obj = normalized["objects"][0]

    assert obj["left"] == 100.0
    assert obj["top"] == 240.0
    assert obj["width"] == 160.0
    assert obj["height"] == 320.0
    assert obj["strokeWidth"] == 8.0
