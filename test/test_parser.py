import json

SEED = "-FAKE-SEED"

def bake(text: str):
    text = text.replace("\r", "")
    
    in_str = False
    escape = False
    in_single = False
    in_multi = False
    
    stack = [] # list of (type, list_of_deferred_comments)
    
    idx = 0
    out = []
    
    header_idx = None
    footer_idx = None
    counter = 0
    
    while idx < len(text):
        c = text[idx]
        
        if in_single:
            if c == '\n':
                in_single = False
                comment = text[comment_start:idx+1]
                key_prefix = '"//'
                
                key = f'{key_prefix}{counter}{SEED}"'
                val = json.dumps(comment[2:])
                
                if stack:
                    if stack[-1][0] == '[':
                        stack[-1][1].append(f'{{{key}: {val}}}')
                    else:
                        stack[-1][1].append(f'{key}: {val}')
                counter += 1
                out.append('\n')
            idx += 1
            continue
            
        if in_multi:
            if c == '*' and idx+1 < len(text) and text[idx+1] == '/':
                in_multi = False
                comment = text[comment_start:idx+2]
                key = f'"/*{counter}{SEED}"'
                val = json.dumps(comment[2:-2])
                
                if stack:
                    if stack[-1][0] == '[':
                        stack[-1][1].append(f'{{{key}: {val}}}')
                    else:
                        stack[-1][1].append(f'{key}: {val}')
                        
                counter += 1
                idx += 2
            else:
                idx += 1
            continue
            
        if in_str:
            out.append(c)
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"':
                in_str = False
            idx += 1
            continue
            
        # Normal
        if c == '"':
            in_str = True
            out.append(c)
            idx += 1
            continue
            
        if c == '/' and idx+1 < len(text):
            if text[idx+1] == '/':
                in_single = True
                comment_start = idx
                if not stack and header_idx is None:
                    # this comment is part of the header
                    # actually, if header_idx isn't set, we are in the header!
                    pass
                idx += 2
                continue
            elif text[idx+1] == '*':
                in_multi = True
                comment_start = idx
                idx += 2
                continue
                
        if c in '{[':
            if not stack:
                header_idx = len("".join(out))
            stack.append((c, []))
            out.append(c)
            idx += 1
            continue
            
        if c in '}]':
            bracket, comments = stack.pop()
            # If we had any components in this container, we must append a comma if it lacked one, OR we just prefix our comments with a comma.
            # wait, if the container is empty `{}`, we don't need a leading comma!
            # if we just output them, we can join with `,`
            if comments:
                # remove trailing whitespace/newlines from out to see if it's empty
                temp = "".join(out)
                last_char = None
                for i in range(len(temp)-1, -1, -1):
                    if not temp[i].isspace():
                        last_char = temp[i]
                        break
                
                if last_char and last_char not in '{[':
                    # it had items, need a comma unless there's already one
                    if last_char != ',':
                        out.append(',')
                
                out.append(",\n".join(comments))
                # json5 allows trailing comma, so we append one
                out.append(",")
            out.append(c)
            if not stack:
                footer_idx = len("".join(out))
            idx += 1
            continue
            
        out.append(c)
        idx += 1
        
    return "".join(out), header_idx, footer_idx

if __name__ == "__main__":
    with open("old.jsonc") as f:
        text = f.read()
    baked, h, f = bake(text)
    print("----- BAKED -----")
    print(baked)
    
    import ujson5
    data = ujson5.loads(baked[h:f])
    print(data)
