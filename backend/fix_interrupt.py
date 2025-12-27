import os

file_path = "/root/sealai/backend/app/services/chat/ws_streaming.py"

with open(file_path, "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "except Exception as exc:" in line:
        # Insert the InterruptSignal handler before the generic Exception handler
        indent = line[:line.find("except")]
        new_lines.append(f'{indent}except InterruptSignal as sig:\n')
        new_lines.append(f'{indent}    await _emit_interrupt_event(ws, chat_id=chat_id, payload=sig.payload)\n')
        new_lines.append(line)
    else:
        new_lines.append(line)

with open(file_path, "w") as f:
    f.writelines(new_lines)

print("Successfully patched ws_streaming.py")
