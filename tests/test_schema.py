import json
import unittest

from ideogram_captioner.schema import normalize_caption, parse_palette_text, serialize_caption


class SchemaTests(unittest.TestCase):
    def test_serializes_compact_json_with_literal_unicode(self):
        text = serialize_caption(
            {
                "high_level_description": "Café sign",
                "style_description": {
                    "aesthetics": "clean",
                    "lighting": "soft",
                    "photo": "50mm",
                    "medium": "photograph",
                },
                "compositional_deconstruction": {"background": "street", "elements": []},
            }
        )

        self.assertNotIn(": ", text)
        self.assertNotIn(", ", text)
        self.assertIn("Café", text)
        self.assertEqual(json.loads(text)["high_level_description"], "Café sign")

    def test_preserves_ideogram_key_order(self):
        text = serialize_caption(
            {
                "style_description": {
                    "aesthetics": "bold",
                    "lighting": "studio",
                    "medium": "graphic_design",
                    "art_style": "flat vector",
                    "color_palette": ["#ffffff", "#123ABC"],
                },
                "compositional_deconstruction": {
                    "background": "paper",
                    "elements": [
                        {
                            "type": "text",
                            "bbox": [100, 200, 300, 400],
                            "text": "SALE",
                            "desc": "large text",
                            "color_palette": ["#ff0000"],
                        }
                    ],
                },
            }
        )

        style_order = [
            '"aesthetics"',
            '"lighting"',
            '"medium"',
            '"art_style"',
            '"color_palette"',
        ]
        self.assertEqual([text.index(key) for key in style_order], sorted(text.index(key) for key in style_order))

        self.assertIn(
            '"elements":[{"type":"text","bbox":[100,200,300,400],"text":"SALE","desc":"large text","color_palette":["#FF0000"]}]',
            text,
        )

    def test_palette_validation_and_bbox_normalization(self):
        colors, invalid = parse_palette_text("#abcDEF, nope #123456 #fff", 2)
        self.assertEqual(colors, ["#ABCDEF", "#123456"])
        self.assertEqual(invalid, ["nope", "#fff"])

        caption = normalize_caption(
            {
                "compositional_deconstruction": {
                    "background": "",
                    "elements": [{"type": "obj", "bbox": [900, -10, 100, 1200], "desc": "box"}],
                }
            }
        )
        self.assertEqual(caption["compositional_deconstruction"]["elements"][0]["bbox"], [100, 0, 900, 1000])


if __name__ == "__main__":
    unittest.main()
