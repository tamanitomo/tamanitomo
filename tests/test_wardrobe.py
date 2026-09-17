import unittest
from kit.app.wardrobe import (
    filter_wardrobe_items,
    is_blacklisted_undergarment,
    is_intimate_garment,
)

class WardrobeFilterTests(unittest.TestCase):
    def test_blacklisted_undergarment_detection(self):
        self.assertTrue(is_blacklisted_undergarment({'description': 'silk panties'}))
        self.assertTrue(is_blacklisted_undergarment({'id': 'thong_01', 'description': 'lace'}))
        self.assertTrue(is_blacklisted_undergarment({'description': 'black boxer briefs'}))
        self.assertTrue(is_blacklisted_undergarment({'category': 'underwear'}))
        self.assertFalse(is_blacklisted_undergarment({'description': 'blue jeans'}))
        self.assertFalse(is_blacklisted_undergarment({'description': 'green tee'}))
        self.assertFalse(is_blacklisted_undergarment('running shoes'))

    def test_intimate_garment_detection(self):
        self.assertTrue(is_intimate_garment({'description': 'lace bralette'}))
        self.assertTrue(is_intimate_garment({'description': 'silk underwear'}))
        self.assertTrue(is_intimate_garment({'category': 'underwear', 'description': 'cotton'}))
        self.assertTrue(is_intimate_garment({'intimate': True, 'description': 'something'}))
        # Sports bra is explicitly allowed as an athletic top
        self.assertFalse(is_intimate_garment({'description': 'supportive sports bra'}))
        self.assertFalse(is_intimate_garment({'description': 'sports-bra'}))
        self.assertFalse(is_intimate_garment({'description': 'summer sundress'}))

    def test_tiered_wardrobe_visibility_stages(self):
        items = [
            {'id': 'dress', 'description': 'red dress'},
            {'id': 'sports_bra', 'description': 'high-impact sports bra'},
            {'id': 'bralette', 'description': 'lace bralette'},
            {'id': 'panties', 'description': 'silk panties'},
        ]

        # Stage < 2 (Just met / Flirting): hides all undergarments; sports bras allowed
        stage1 = filter_wardrobe_items(items, stage=1)
        self.assertEqual([i['id'] for i in stage1], ['dress', 'sports_bra'])

        # Stage 2-3 (Chemistry / Intimacy): shows all except blacklisted undergarments (panties/boxers/thong)
        stage2 = filter_wardrobe_items(items, stage=2)
        self.assertEqual([i['id'] for i in stage2], ['dress', 'sports_bra', 'bralette'])

        stage3 = filter_wardrobe_items(items, stage=3)
        self.assertEqual([i['id'] for i in stage3], ['dress', 'sports_bra', 'bralette'])

        # Stage >= 4 (Bonded): unrestricted
        stage4 = filter_wardrobe_items(items, stage=4)
        self.assertEqual([i['id'] for i in stage4], ['dress', 'sports_bra', 'bralette', 'panties'])

if __name__ == '__main__':
    unittest.main()
