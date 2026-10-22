import os
import cv2
import numpy as np
from PIL import Image
import trimesh

scene = trimesh.load('core/female_face_extracted/scene.gltf')

# 11 angles covering the full range of yaw [-0.20, +0.20] radians
angles = np.linspace(-0.20, 0.20, 11)

for idx, dyaw in enumerate(angles):
    sc = scene.copy()
    rot = trimesh.transformations.rotation_matrix(-np.pi / 2 + dyaw, [0, 1, 0])
    sc.apply_transform(rot)
    png = sc.save_image(resolution=(512, 512))
    
    raw = Image.open(trimesh.util.wrap_as_stream(png)).convert('RGB')
    arr = np.array(raw)
    
    # Clean background alpha mask
    dist = 255 - np.min(arr, axis=2)
    alpha = np.clip((dist / 20.0) * 255.0, 0, 255).astype(np.uint8)
    
    # Smooth holographic blue grading
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r = np.clip(gray * 20 + (gray ** 2) * 110, 0, 255)
    g = np.clip(gray * 140 + (gray ** 1.5) * 100 + 15, 0, 255)
    b = np.clip(gray * 190 + (gray ** 1.2) * 45 + 40, 0, 255)
    holo_rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
    
    # ── 1. Idle Base ──
    idle_arr = np.dstack([holo_rgb, alpha])
    Image.fromarray(idle_arr).save(f'core/female_yaw_{idx}_idle.png')
    
    h, w, _ = idle_arr.shape
    mx = int(256 + dyaw * 120)
    my = 312
    
    # ── 2. Organic Speaking Mouth (NO cut-out rectangles!) ──
    map_x, map_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    dx_m = (map_x - mx) / 18.0
    dy_m = (map_y - my) / 16.0
    warp_m = (np.abs(dx_m) < 1.0) & (dy_m > 0.0) & (dy_m < 1.0)
    drop_m = np.zeros_like(map_y)
    drop_m[warp_m] = 3.5 * (1.0 - dx_m[warp_m]**2) * np.sin(dy_m[warp_m] * np.pi)
    warped_m = cv2.remap(idle_arr, map_x, map_y - drop_m, cv2.INTER_LINEAR)
    
    cavity = np.zeros((h, w), dtype=np.float32)
    cv2.ellipse(cavity, (mx, my + 1), (14, 3), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    cavity = cv2.GaussianBlur(cavity, (3, 3), 0)[:, :, None]
    
    teeth = np.zeros((h, w), dtype=np.float32)
    cv2.ellipse(teeth, (mx, my), (11, 2), 0, 0, 180, 1.0, -1, cv2.LINE_AA)
    teeth = cv2.GaussianBlur(teeth, (3, 3), 0)[:, :, None]
    
    dark_col = np.array([3, 18, 38, 255], dtype=np.float32)
    teeth_col = np.array([125, 215, 245, 210], dtype=np.float32)
    
    speak_res = warped_m.astype(np.float32) * (1.0 - cavity) + dark_col * cavity
    speak_res = speak_res * (1.0 - teeth * 0.55) + teeth_col * (teeth * 0.55)
    speak_arr = np.clip(speak_res, 0, 255).astype(np.uint8)
    Image.fromarray(speak_arr).save(f'core/female_yaw_{idx}_speak.png')
    
    # ── 3. Natural Eyelid Blinking ──
    ex_l = int(210 + dyaw * 115)
    ex_r = int(302 + dyaw * 115)
    ey = 226
    
    skin_val = np.mean(idle_arr[210:216, 210:220], axis=(0, 1)).astype(np.float32)
    blink_res = idle_arr.copy().astype(np.float32)
    
    for ex in [ex_l, ex_r]:
        socket = np.zeros((h, w), dtype=np.float32)
        cv2.ellipse(socket, (ex, ey), (19, 10), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
        socket = cv2.GaussianBlur(socket, (5, 5), 0)[:, :, None]
        blink_res = blink_res * (1.0 - socket) + skin_val * socket
        
        pts = []
        for x in range(ex - 19, ex + 20):
            t = (x - ex) / 19.0
            y = int(ey + 1 + 2.5 * (1.0 - t**2))
            pts.append((x, y))
        for i in range(len(pts) - 1):
            cv2.line(blink_res, pts[i], pts[i+1], (4, 20, 42, 255), 2, cv2.LINE_AA)
            
    blink_arr = np.clip(blink_res, 0, 255).astype(np.uint8)
    Image.fromarray(blink_arr).save(f'core/female_yaw_{idx}_blink.png')
    print(f'Angle {idx}/10 done (dyaw={dyaw:.3f})')

print('All 33 frames successfully generated!')
