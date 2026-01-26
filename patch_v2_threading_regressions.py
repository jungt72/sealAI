import re
import os

def patch_file(path, replacements):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    with open(path, 'r') as f:
        content = f.read()
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"Applied patch to {path} using string replace")
        else:
            print(f"Pattern not found in {path}: {old[:50]}...")
            
    with open(path, 'w') as f:
        f.write(content)

# 1. Patch langgraph_v2.py
lg_path = '/home/thorsten/sealai/backend/app/api/v1/endpoints/langgraph_v2.py'

lg_repl = []

# Fix messy duplicated import
messy_import = "from app.langgraph_v2.utils.threading import reset_current_tenant_id, set_current_tenant_id, resolve_checkpoint_thread_id, resolve_checkpoint_thread_id, resolve_checkpoint_thread_id"
clean_import = "from app.langgraph_v2.utils.threading import reset_current_tenant_id, set_current_tenant_id, resolve_checkpoint_thread_id"

lg_repl.append((messy_import, clean_import))

# If clean import is not there (and messy isn't), maybe original is there?
# We won't add logic for original here because we know we patched it.
# BUT just in case:
# original_import = "from app.langgraph_v2.utils.threading import reset_current_tenant_id, set_current_tenant_id"
# We skip that to avoid duplication if messy exists.

# Fix resolve_checkpoint_thread_id call to use user.sub
# Search for block with scoped_user_id
bad_call_block = """    checkpoint_thread_id = resolve_checkpoint_thread_id(
        tenant_id=tenant_id,
        user_id=scoped_user_id,
        chat_id=request.chat_id,
    )"""

good_call_block = """    checkpoint_thread_id = resolve_checkpoint_thread_id(
        tenant_id=tenant_id,
        user_id=user.sub,
        chat_id=request.chat_id,
    )"""

lg_repl.append((bad_call_block, good_call_block))

patch_file(lg_path, lg_repl)


# 2. Patch state.py
st_path = '/home/thorsten/sealai/backend/app/api/v1/endpoints/state.py'
st_repl = []

# Fix import in state.py
# The grep showed "from app.langgraph_v2.utils.threading import reset_current_tenant_id, set_current_tenant_id"
# We want to append resolve_checkpoint_thread_id
st_import_old = "from app.langgraph_v2.utils.threading import reset_current_tenant_id, set_current_tenant_id"
st_import_new = "from app.langgraph_v2.utils.threading import reset_current_tenant_id, set_current_tenant_id, resolve_checkpoint_thread_id"

# We only replace if not already replaced.
st_repl.append((st_import_old, st_import_new))

# Note: The _resolve_owner_ids logic was already updated in the file (if previous step worked).
# But if we need to verify: 
# Since we didn't confirm failure of that part (it failed on NameError of resolve_checkpoint_thread_id later),
# we assume the injection of _resolve_owner_ids worked.
# Wait, previous traceback: "NameError: name 'resolve_checkpoint_thread_id' is not defined".
# Line: "resolved_key = resolve_checkpoint_thread_id(..."
# This means the CALL was there (so injection worked), but IMPORT was missing.

patch_file(st_path, st_repl)

