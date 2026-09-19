"""Emergency CLI PIN reset and status management."""
from __future__ import annotations
import companion_config as cc
from .common import print, resolve

def cmd_pin(args):
    """View, update, or clear the remote access network PIN for this companion."""
    c = resolve(args, require_config=False)
    if getattr(args, 'clear', False):
        c.remote_pin = ''
        cc.save_access_pin(c.hermes_root,c.remote_pin)
        print(f"Workspace remote PIN cleared. Remote access is now open to your local network without a PIN.")
        return 0

    pin_value = getattr(args, 'set', None)
    if pin_value is not None:
        pin = str(pin_value).strip()
        if pin and (not pin.isdigit() or len(pin) != 4):
            raise ValueError('PIN must be a 4-digit numeric code (e.g. 1234), or empty')
        c.remote_pin = pin
        cc.save_access_pin(c.hermes_root,c.remote_pin)
        if pin:
            print(f"Workspace remote PIN configured.")
        else:
            print(f"Workspace remote PIN cleared.")
        return 0

    c.remote_pin=cc.access_pin(c.hermes_root,c.remote_pin)
    # Read-only check
    if c.remote_pin:
        print(f"Workspace remote PIN is CONFIGURED.")
        print(f"  To clear: tamanitomo pin --clear")
        print(f"  To update: tamanitomo pin --set <4-digit-PIN>")
    else:
        print(f"No workspace remote PIN configured. Remote access is open on your local network.")
        print(f"  To set a PIN: tamanitomo pin --set <4-digit-PIN>")
    return 0
