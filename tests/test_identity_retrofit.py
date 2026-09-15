import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"kit/scripts"))
import companion_identity as identity


def test_retrofit_preserves_prose_and_replaces_empty_placeholders():
    prose='Intro\n\n## Core Identity\nA thoughtful person.\n\n## Physical Description\nAn adult with green eyes.\n\n## Voice and Tone\nWarm.\n'
    original=prose+'\n<!-- COMPANION-SECTION:appearance LOCKED -->\n<!-- /COMPANION-SECTION:appearance -->\n'
    result=identity.retrofit(original)
    assert identity.sections(result)['appearance']['body']=='## Physical Description\nAn adult with green eyes.'
    assert identity.sections(result)['appearance']['locked']
    assert identity.retrofit(result)==result
    import re
    strip=lambda text:re.sub(r'<!--\s*/?COMPANION-SECTION:[^>]+-->','',text).split()
    assert strip(original)==strip(result)


def test_retrofit_keeps_authored_markers_and_self_block():
    original='<!-- COMPANION-SECTION:core -->\n## Core Identity\nMine.\n<!-- /COMPANION-SECTION:core -->\n## Voice and Tone\nWarm.\n<!-- COMPANION-SELF-AUTHORED:BEGIN -->\nMy words.\n<!-- COMPANION-SELF-AUTHORED:END -->\n'
    result=identity.retrofit(original)
    assert identity.sections(result)['core']['body']==identity.sections(original)['core']['body']
    assert 'My words' not in identity.sections(result)['voice']['body']
    assert result.endswith('<!-- COMPANION-SELF-AUTHORED:BEGIN -->\nMy words.\n<!-- COMPANION-SELF-AUTHORED:END -->\n')

class RetrofitTests(unittest.TestCase):
    test_preserves=staticmethod(test_retrofit_preserves_prose_and_replaces_empty_placeholders)
    test_self_block=staticmethod(test_retrofit_keeps_authored_markers_and_self_block)
