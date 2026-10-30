; Leased ATV gearing/drive, native tire grip and baseline aerodynamic drag.
BITS 64
ORG 0
%define FRAME 0x180
entry:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov dword [rsp+0xF4], 1
    jmp save_common
times 64-($-$$) db 0xCC
entry_transmission:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov dword [rsp+0xF4], 2
    jmp save_common
times 128-($-$$) db 0xCC
entry_wheel_limit:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov dword [rsp+0xF4], 3
    jmp save_common
times 192-($-$$) db 0xCC
entry_longitudinal_grip:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov dword [rsp+0xF4], 4
    jmp save_common
times 256-($-$$) db 0xCC
entry_lateral_grip:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov dword [rsp+0xF4], 5
    jmp save_common
times 320-($-$$) db 0xCC
entry_aero:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov dword [rsp+0xF4], 6
save_common:
    mov [rsp+0x28], rcx
    mov [rsp+0x30], rdx
    mov [rsp+0x38], r8
    mov [rsp+0x40], r9
    mov [rsp+0x48], r10
    mov [rsp+0x50], r11
    mov [rsp+0x58], rdi
    movdqu [rsp+0x60], xmm0
    movdqu [rsp+0x70], xmm1
    movdqu [rsp+0x80], xmm2
    movdqu [rsp+0x90], xmm3
    movdqu [rsp+0xA0], xmm4
    movdqu [rsp+0xB0], xmm5
    mov qword [rsp+0xE0], 0
    mov dword [rsp+0xF8], 0
    lea r10, [rel header]
    cmp dword [rsp+0xF4], 6
    jne .not_aero
    mov rdi, rbx           ; original aerodynamic solver owns its current Pfx in RBX
    lock inc qword [r10+512]
    jmp .calls_counted
.not_aero:
    cmp dword [rsp+0xF4], 4
    jb .not_grip
    mov rdi, rsi           ; native tire solver keeps the current Pfx in RSI
    lock inc qword [r10+448]
    jmp .calls_counted
.not_grip:
    cmp dword [rsp+0xF4], 3
    jne .other_calls
    mov rdi, rbx           ; this native wheel-physics caller owns Pfx in RBX
    lock inc qword [r10+416]
    jmp .calls_counted
.other_calls:
    cmp dword [rsp+0xF4], 2
    je .torque_call
    lock inc qword [r10+256]
    jmp .calls_counted
.torque_call:
    lock inc qword [r10+320]
.calls_counted:
    mov rax, [r10+64]
    test rax, 1
    jnz finish
    mov [rsp+0xC0], rax
    mov rax, [r10+72]
    test rax, rax
    jz finish
    mov [rsp+0xC8], rax
    cmp rdi, [r10+160]
    jne finish
    mov dword [r10+304], 1
clock:
    lea rcx, [rsp+0xD0]
    mov rax, [r10+32]
    call [rax]
    lea r10, [rel header]
    test eax, eax
    jz fallback
    mov rax, [rsp+0xD0]
    cmp rax, [rsp+0xC8]
    jae fallback
validate:
    mov rax, [rsp+0xC0]
    cmp rax, [r10+64]
    jne fallback
    mov dword [r10+304], 2
    cmp rdi, [r10+160]
    jne fallback
    mov rax, [r10+176]
    cmp [rdi], rax
    jne fallback
    mov eax, [rdi+0x2DC]
    cmp eax, [r10+168]
    jne fallback
    cmp dword [rsp+0xF4], 1
    je .transmission_bound
    mov rax, [rdi+0x1ED8]
    cmp rax, [r10+384]
    jne fallback
    cmp dword [rsp+0xF4], 2
    jne .transmission_bound
    mov rax, [rsp+0x28]
    cmp rax, [r10+384]
    jne fallback
    cmp rax, [rdi+0x1ED8]
    jne fallback
    mov rax, [rsp+0x30]
    cmp [rax+0x10], rdi
    jne fallback
.transmission_bound:
    mov rax, [r10+48]
    mov rax, [rax]
    test rax, rax
    jz fallback
    cmp dword [rax+0x48], 7
    jne fallback
    cmp byte [rax+0x7C], 0
    je fallback
    mov dword [r10+304], 3
    mov rax, [r10+184]
    mov rax, [rax]
    test rax, rax
    jz fallback
    mov rax, [rax+0x20290]
    cmp rax, [r10+104]
    jne fallback
    test rax, rax
    jz fallback
    mov ecx, [rax+0x120]
    dec ecx
    cmp ecx, 65535
    ja fallback
    mov rcx, [rax+8]
    cmp rcx, [r10+112]
    jne fallback
    test rcx, rcx
    jz fallback
    cmp qword [rax], 0
    je fallback
    mov eax, [r10+96]
    mov r8, [r10+120]
    call resolve_source
    test rax, rax
    jz fallback
    cmp dword [rax+0x170], 1
    jne fallback
    mov rcx, [r10+80]
    cmp [rax+0xB8], rcx
    jne fallback
    mov edx, [r10+152]
    cmp [rax+0x120], edx
    jne fallback
    mov dword [r10+304], 4
    mov rax, [r10+56]
    mov rax, [rax]
    test rax, rax
    jz fallback
    mov rax, [rax+0x60]
    test rax, rax
    jz fallback
    cmp [rax+0x170], rcx
    jne fallback
    mov rax, [r10+24]
    add rax, 0x1A60028
    cmp [rcx], rax
    jne fallback
    mov eax, [r10+96]
    cmp [rcx+0x2098], eax
    jne fallback
    mov rax, [rcx+0x2400]
    sub rax, 0x10
    cmp rax, [r10+88]
    jne fallback
    mov rdx, [r10+24]
    add rdx, 0x1EE24A0
    cmp [rax], rdx
    jne fallback
    cmp [rax+0x68], rcx
    jne fallback
    mov dword [r10+304], 5
    mov eax, [r10+144]
    mov r8, [r10+136]
    call resolve_source
    test rax, rax
    jz fallback
    cmp dword [rax+0x170], 2
    jne fallback
    mov ecx, [r10+96]
    cmp [rax+0x54], ecx
    jne fallback
    mov rcx, [r10+128]
    lea rdx, [rcx+8]
    cmp [rax+0x40], rdx
    jne fallback
    mov rax, [r10+24]
    add rax, 0x1F59DA0
    cmp [rcx], rax
    jne fallback
    mov rax, [r10+24]
    add rax, 0x1F5A248
    cmp [rcx+8], rax
    jne fallback
    mov eax, [r10+144]
    cmp [rcx+0x4A28], eax
    jne fallback
    mov eax, [r10+152]
    cmp [rcx+0x5020], eax
    jne fallback
    cmp [rcx+0x4A98], rdi
    jne fallback
    mov rax, [rsp+0xC0]
    cmp rax, [r10+64]
    jne fallback
    cmp dword [rsp+0xF8], 0
    jne scaled
    mov dword [rsp+0xF8], 1
    jmp clock              ; close the entire current-driver binding after QPC
scaled:
    cmp dword [rsp+0xF4], 6
    je scaled_aero
    cmp dword [rsp+0xF4], 4
    jae scaled_grip
    cmp dword [rsp+0xF4], 3
    je scaled_wheel_limit
    cmp dword [rsp+0xF4], 2
    jne scaled_speed
    ; The engine field is never modified. All adaptation is stack-local to
    ; this transmission call, including its native auto-shift/physics helpers.
    mov eax, [rdi+0x1EE4]
    mov edx, eax
    and eax, 0x7FFFFFFF
    mov dword [rsp+0xE8], 0x3F800000
    test eax, eax
    jz .torque_valid
    cmp eax, 0x00800000
    jb fallback
    test edx, 0x80000000
    jnz .engine_brake
    cmp eax, 0x7E800000   ; positive *4 must remain finite
    jae fallback
    mov dword [rsp+0xE8], 0x40800000
    jmp .torque_valid
.engine_brake:
    cmp eax, 0x7F000000   ; negative *2 cancels the halved final drive
    jae fallback
    mov dword [rsp+0xE8], 0x40000000
.torque_valid:
    mov rcx, [rsp+0x28]
    mov eax, [rcx+0x54]
    cmp eax, 0x01000000   ; the halved final drive must stay normal and positive
    jb fallback
    cmp eax, 0x7F800000
    jae fallback
    ; Only 0x00..0x7F are copied. Runtime state is embedded at original T+0x80.
%assign block 0
%rep 8
    movdqu xmm0, [rcx+block]
    movdqu [rsp+0x100+block], xmm0
%assign block block+16
%endrep
    movss xmm0, [rsp+0x154]
    mulss xmm0, [rel half]
    movss [rsp+0x154], xmm0
    ; A positive alternate low-range final drive uses the same ratio change;
    ; native sentinel 0/-1/NaN and the low-gear count/selection stay untouched.
    movss xmm0, [rsp+0x13C]
    xorps xmm1, xmm1
    ucomiss xmm0, xmm1
    jbe .low_done
    jp .low_done
    mov eax, [rsp+0x13C]
    cmp eax, 0x01000000
    jb fallback
    cmp eax, 0x7F800000
    jae fallback
    mulss xmm0, [rel half]
    movss [rsp+0x13C], xmm0
.low_done:
    ; Preflight the same native multiply order, including reverse/low range,
    ; so an overflowing effective wheel torque falls back to the original call.
    movss xmm1, [rsp+0x154]
    cmp byte [rcx+0x84], 0
    je .range_ready
    movss xmm0, [rsp+0x13C]
    xorps xmm2, xmm2
    comiss xmm0, xmm2
    jbe .range_ready
    movaps xmm1, xmm0
.range_ready:
    cmp byte [rdi+0x1EE0], 0
    je .forward
    movss xmm0, [rcx+0x5C]
    xorps xmm0, [rel sign_mask]
    jmp .ratio_ready
.forward:
    movsx eax, byte [rcx+0xE5]
    test eax, eax
    js fallback
    cmp eax, [rcx+0x68]
    jae fallback
    mov rdx, [rcx+0x60]
    movss xmm0, [rdx+rax*4]
.ratio_ready:
    mulss xmm0, xmm1
    mulss xmm0, [rdi+0x1EE4]
    mulss xmm0, [rsp+0xE8]
    movd eax, xmm0
    and eax, 0x7FFFFFFF
    cmp eax, 0x7F800000
    jae fallback
    movss [r10+400], xmm0
    mov qword [rsp+0xE0], 1
    lock inc qword [r10+328]
    movss xmm0, [rdi+0x1EE4]
    movss [r10+336], xmm0
    mulss xmm0, [rsp+0xE8]
    movss [r10+340], xmm0
    movss xmm0, [rcx+0x54]
    movss [r10+392], xmm0
    movss xmm0, [rsp+0x154]
    movss [r10+396], xmm0
    jmp scaled_record
scaled_aero:
    mov rcx, [rsp+0x28]
    cmp rcx, [rdi+0x4D0]
    jne fallback
    mov eax, [rcx+8]
    ; Preserve zero, subnormal, underflow, negative and nonfinite inputs.
    cmp eax, 0x01000000
    jb fallback
    cmp eax, 0x7F800000
    jae fallback
    movss xmm0, [rcx+8]
    movss [r10+536], xmm0
    mulss xmm0, [rel half]
    movss [r10+540], xmm0
    mov qword [rsp+0xE0], 1
    lock inc qword [r10+520]
    jmp scaled_record
scaled_wheel_limit:
    ; The later wheel integrator still queries the original transmission.
    ; Its RPM clamp must agree with the call-scoped halved final drive.
    mov qword [rsp+0xE0], 1
    lock inc qword [r10+424]
    jmp scaled_record
scaled_grip:
    mov rcx, [rdi+0x12B8]
    cmp rbx, rcx
    jb fallback
    mov edx, [rdi+0x12D0]
    test edx, edx
    jz fallback
    cmp edx, 64
    ja fallback
    imul rdx, rdx, 0x1F0
    mov rax, rbx
    sub rax, rcx
    cmp rax, rdx
    jae fallback
    xor edx, edx
    mov ecx, 0x1F0
    div ecx
    test edx, edx
    jnz fallback
    cmp dword [rbx+0x20], 0x7FFFFFFF
    je fallback           ; no tire force is introduced without native contact
    mov eax, [rbx+0x188]
    cmp eax, 0x7F800000
    jae fallback
    cmp dword [rsp+0xF4], 4
    jne .lateral
    movaps xmm0, [rsp+0x60]
    jmp .limit_ready
.lateral:
    movaps xmm0, xmm7
.limit_ready:
    movd eax, xmm0
    and eax, 0x7FFFFFFF
    cmp eax, 0x7F800000
    jae fallback
    ; Keep the original curve, Fz, combined-slip shape and material factors.
    ; Only the signed grip ceiling changes; native demand clamps remain intact.
    mulss xmm0, [rbx+0x188]
    movd eax, xmm0
    and eax, 0x7FFFFFFF
    cmp eax, 0x7F000000
    jae fallback
    movss [r10+472], xmm0
    addss xmm0, xmm0
    movss [r10+476], xmm0
    mov eax, [rsp+0xF4]
    sub eax, 3
    mov [r10+480], eax
    mov [r10+488], rbx
    mov qword [rsp+0xE0], 1
    lock inc qword [r10+456]
    jmp scaled_record
scaled_speed:
    mov qword [rsp+0xE0], 1
    lock inc qword [r10+264]
    movss xmm0, [rdi+0x2DC]
    movss [r10+280], xmm0
    addss xmm0, xmm0
    movss [r10+284], xmm0
scaled_record:
    mov [r10+288], rdi
    mov rax, [rsp+0xD0]
    mov [r10+296], rax
    mov dword [r10+304], 0
    jmp finish
fallback:
    cmp dword [rsp+0xF4], 6
    jne .not_aero
    lock inc qword [r10+528]
    jmp finish
.not_aero:
    cmp dword [rsp+0xF4], 4
    jb .not_grip
    lock inc qword [r10+464]
    jmp finish
.not_grip:
    cmp dword [rsp+0xF4], 3
    jne .other
    lock inc qword [r10+432]
    jmp finish
.other:
    cmp dword [rsp+0xF4], 2
    jne .speed
    lock inc qword [r10+352]
    jmp finish
.speed:
    lock inc qword [r10+272]
finish:
    movdqu xmm5, [rsp+0xB0]
    movdqu xmm4, [rsp+0xA0]
    movdqu xmm3, [rsp+0x90]
    movdqu xmm2, [rsp+0x80]
    movdqu xmm1, [rsp+0x70]
    movdqu xmm0, [rsp+0x60]
    mov rax, [rsp+0x20]
    mov rcx, [rsp+0x28]
    mov rdx, [rsp+0x30]
    mov r8, [rsp+0x38]
    mov r9, [rsp+0x40]
    mov r10, [rsp+0x48]
    mov r11, [rsp+0x50]
    mov rdi, [rsp+0x58]
    cmp dword [rsp+0xF4], 6
    je .aero
    cmp dword [rsp+0xF4], 4
    jae .grip
    cmp dword [rsp+0xF4], 3
    je .wheel_limit
    cmp dword [rsp+0xF4], 2
    je .transmission
    movss xmm1, [rdi+0x2DC] ; exact original instruction, including upper-lane clearing
    cmp qword [rsp+0xE0], 1
    jne .return
    addss xmm1, xmm1
    jmp .return
.aero:
    movss xmm1, [rcx+8]    ; original load; the shared aerodynamic profile is never written
    cmp qword [rsp+0xE0], 1
    jne .aero_return
    mulss xmm1, [rel half] ; original high-drag endpoint, blending and lift remain native
.aero_return:
    push qword [rsp+FRAME]
    popfq
    lea rsp, [rsp+FRAME+8]
    ret
.transmission:
    cmp qword [rsp+0xE0], 1
    jne .original_call
    lea rcx, [rsp+0x100]
    mov r8, [rsp+0x28]
    add r8, 0x80
    push qword [rsp+FRAME]
    popfq
    call adapted_transmission
    mov [rsp+0xD0], rax
    movdqu [rsp+0xD8], xmm0
    mov rax, [rsp+0x28]
    movss xmm0, [rax+0xA0]  ; actual original runtime output, including clutch=0
    movss [rel header+400], xmm0
    movdqu xmm0, [rsp+0xD8]
    mov rax, [rsp+0xD0]
    lea rsp, [rsp+FRAME+8]
    ret
.original_call:
    push qword [rsp+FRAME]
    popfq
    lea rsp, [rsp+FRAME+8]
    jmp qword [rel header+360] ; exact original 1E5DB0 once, real runtime T+0x80
.wheel_limit:
    add qword [rsp+FRAME+8], 1 ; the displaced indirect CALL is six bytes
    cmp qword [rsp+0xE0], 1
    jne .original_wheel_limit
    push qword [rsp+FRAME]
    popfq
    call qword [rax+0x370]
    movss [rel header+440], xmm0
    addss xmm0, xmm0
    movss [rel header+444], xmm0
    lea rsp, [rsp+FRAME+8]
    ret
.original_wheel_limit:
    push qword [rsp+FRAME]
    popfq
    call qword [rax+0x370]
    lea rsp, [rsp+FRAME+8]
    ret
.grip:
    add qword [rsp+FRAME+8], 3 ; both displaced scalar multiplies are eight bytes
    cmp dword [rsp+0xF4], 4
    jne .lateral_grip
    cmp qword [rsp+0xE0], 1
    jne .original_longitudinal_grip
    push qword [rsp+FRAME]
    popfq
    mulss xmm0, [rbx+0x188]
    addss xmm0, xmm0
    lea rsp, [rsp+FRAME+8]
    ret
.original_longitudinal_grip:
    push qword [rsp+FRAME]
    popfq
    mulss xmm0, [rbx+0x188]
    lea rsp, [rsp+FRAME+8]
    ret
.lateral_grip:
    cmp qword [rsp+0xE0], 1
    jne .original_lateral_grip
    push qword [rsp+FRAME]
    popfq
    mulss xmm7, [rbx+0x188]
    addss xmm7, xmm7
    lea rsp, [rsp+FRAME+8]
    ret
.original_lateral_grip:
    push qword [rsp+FRAME]
    popfq
    mulss xmm7, [rbx+0x188]
    lea rsp, [rsp+FRAME+8]
    ret
.return:
    ; Skip the full displaced instruction even if close restores it in flight.
    add qword [rsp+FRAME+8], 3
    push qword [rsp+FRAME]
    popfq
    lea rsp, [rsp+FRAME+8]
    ret

; Handle EAX -> current active generation-map source, equal to expected R8.
resolve_source:
    test ax, ax
    jz .no
    mov r9d, eax
    shr eax, 16
    mov rcx, [r10+104]
    cmp eax, [rcx+0x120]
    jae .no
    mov rdx, [r10+112]
    mov eax, [rdx+rax*4]
    cmp ax, r9w
    jne .no
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rcx]
    cmp rax, r8
    jne .no
    shr r9d, 16
    cmp [rax+0x174], r9w
    jne .no
    test byte [rax+0x17C], 1
    jz .no
    ret
.no:
    xor eax, eax
    ret

times 3584-($-$$) db 0xCC
; Exact 1F2160..1F220E prefix: native relative branches use local labels,
; its single RIP scalar sign-mask load uses the identical local bit pattern.
; No original CALL is inside the displaced prefix. All remaining code runs
; at the original continuation, including its original register/stack epilogue.
adapted_transmission:
    push rbx
    push rbp
    push rsi
    push rdi
    sub rsp, 0xB8
    mov rax, [rdx+0x10]
    mov rbx, r8
    movaps [rsp+0x80], xmm7
    mov rsi, rdx
    movaps [rsp+0x40], xmm11
    mov rdi, rcx
    cmp byte [rax+0x1EE0], 0
    jne .reverse
    xor bpl, bpl
    jmp .direction_ready
.reverse:
    cmp byte [r8+0x64], 0
    jne .reverse_ready
    mov eax, [rcx+0x58]
    mov [r8+0x68], eax
    mov byte [r8+0x66], 1
.reverse_ready:
    mov bpl, 1
.direction_ready:
    cmp byte [r8+0x66], 0
    movss xmm11, [rel sign_mask]
    mov [r8+0x64], bpl
    je .engaged
    xorps xmm7, xmm7
    xorps xmm0, xmm0
    jmp .native_continue
.engaged:
    mov rax, [rdx+0x10]
    test bpl, bpl
    je .forward
    movss xmm0, [rcx+0x5C]
    xorps xmm0, xmm11
    jmp .gear_ready
.forward:
    movsx rdx, byte [r8+0x65]
    mov rcx, [rcx+0x60]
    movss xmm0, [rcx+rdx*4]
.gear_ready:
    cmp byte [r8+4], 0
    xorps xmm7, xmm7
    je .normal_range
    movss xmm1, [rdi+0x3C]
    comiss xmm1, xmm7
    ja .range_ready
.normal_range:
    movss xmm1, [rdi+0x54]
.range_ready:
    mulss xmm0, xmm1
    mulss xmm0, [rax+0x1EE4]
    mulss xmm0, [rsp+0x1C8] ; private caller-frame scalar, no Pfx/input writes
.native_continue:
    jmp qword [rel header+368]
align 16, db 0
half: dd 0.5
align 16, db 0
sign_mask: dd 0x80000000, 0, 0, 0
times 4096-($-$$) db 0
header:
