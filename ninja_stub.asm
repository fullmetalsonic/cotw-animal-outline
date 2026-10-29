; NASM flat x64 PIC. Original event calculation always executes. Only the
; verified local source's movement/vehicle hearing addend is suppressed.
BITS 64
ORG 0
%define FRAME 0x108
%define SEQUENCE 0xC0
%define DEADLINE 0xC8
%define QPC 0xD0

entry:
    sub rsp, FRAME               ; aligned calls and 32-byte shadow space
    call [rel header+40]         ; original 5F0D00, original RCX/DL/R8 args
    ; Preserve the ORIGINAL call's volatile return state around our checks.
    mov [rsp+0x20], rax
    mov [rsp+0x28], rcx
    mov [rsp+0x30], rdx
    mov [rsp+0x38], r8
    mov [rsp+0x40], r9
    mov [rsp+0x48], r10
    mov [rsp+0x50], r11
    movdqu [rsp+0x60], xmm0
    movdqu [rsp+0x70], xmm1
    movdqu [rsp+0x80], xmm2
    movdqu [rsp+0x90], xmm3
    movdqu [rsp+0xA0], xmm4
    movdqu [rsp+0xB0], xmm5
    lea r10, [rel header]
    lock inc qword [r10+256]
    mov r11, [r10+64]
    test r11, 1
    jnz fallback
    mov [rsp+SEQUENCE], r11
    mov rax, [r10+72]
    test rax, rax
    jz fallback
    mov [rsp+DEADLINE], rax
    cmp rsi, [r10+88]             ; engine-owned current source record
    jne fallback
    cmp dword [rsi+0x170], 1
    jne fallback
    test byte [rsi+0x17C], 1
    jz fallback
    mov r9, [r10+80]             ; local character
    cmp [rsi+0xB8], r9
    jne fallback
    mov rax, [r10+208]
    cmp [r9], rax
    jne fallback
    ; Live world and canonical local-player binding, never a proximity guess.
    mov rax, [r10+224]
    mov rax, [rax]
    test rax, rax
    jz fallback
    cmp dword [rax+0x48], 7
    jne fallback
    cmp byte [rax+0x7C], 0
    je fallback
    mov rax, [r10+48]
    mov rax, [rax]
    test rax, rax
    jz fallback
    mov rax, [rax+0x60]
    test rax, rax
    jz fallback
    cmp [rax+0x170], r9
    jne fallback
    mov rax, [r9+0x2400]
    sub rax, 0x10
    cmp rax, [r10+112]
    jne fallback
    mov rdx, [r10+216]
    cmp [rax], rdx
    jne fallback
    cmp [rax+0x68], r9
    jne fallback
    ; Resolve the local sense handle through the current generation map.
    mov eax, [r9+0x2098]
    cmp rax, [r10+96]
    jne fallback
    test ax, ax
    jz fallback
    mov r8d, eax
    shr eax, 16
    cmp [rsi+0x174], ax
    jne fallback
    mov rdx, [r10+56]
    mov rdx, [rdx]
    test rdx, rdx
    jz fallback
    mov rdx, [rdx+0x20290]
    cmp rdx, [r10+104]
    jne fallback
    cmp eax, [rdx+0x120]
    jae fallback
    mov rcx, [rdx+8]
    cmp rcx, [r10+120]
    jne fallback
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne fallback
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, rsi
    jne fallback
    cmp r11, [r10+64]
    jne fallback
    lea rcx, [rsp+QPC]
    mov rax, [r10+32]
    call [rax]                  ; game's QPC IAT; preserves XMM6..15
    test eax, eax
    jz fallback
    mov rax, [rsp+QPC]
    cmp rax, [rsp+DEADLINE]
    jae fallback
    lea r10, [rel header]
    mov r11, [rsp+SEQUENCE]
    cmp r11, [r10+64]
    jne fallback
    mov r9, [r10+80]
    cmp [rsi+0xB8], r9
    jne fallback
    mov eax, [r9+0x2098]
    cmp rax, [r10+96]
    jne fallback
    ; Diagnostic data lives solely in our RW allocation, never game objects.
    movss xmm0, [rsp+0x60]
    movss [r10+288], xmm0        ; original event return, preserved below
    movss [r10+292], xmm6
    movss [r10+296], xmm7
    movaps xmm0, xmm6
    maxss xmm0, xmm7
    mulss xmm0, xmm9
    movss [r10+300], xmm0        ; removed movement addend before filtering
    mov [r10+304], rsi
    mov rax, [rsp+QPC]
    mov [r10+312], rax
    mov [r10+280], r11
    lock inc qword [r10+264]
    xorps xmm6, xmm6             ; only intentional nonvolatile changes
    xorps xmm7, xmm7             ; consumed/restored by original caller
    jmp restore
fallback:
    lea r10, [rel header]
    lock inc qword [r10+272]
restore:
    movdqu xmm0, [rsp+0x60]
    movdqu xmm1, [rsp+0x70]
    movdqu xmm2, [rsp+0x80]
    movdqu xmm3, [rsp+0x90]
    movdqu xmm4, [rsp+0xA0]
    movdqu xmm5, [rsp+0xB0]
    mov rax, [rsp+0x20]
    mov rcx, [rsp+0x28]
    mov rdx, [rsp+0x30]
    mov r8, [rsp+0x38]
    mov r9, [rsp+0x40]
    mov r10, [rsp+0x48]
    mov r11, [rsp+0x50]
    add rsp, FRAME
    ret                         ; original 5EC971, event XMM0 unchanged

times 4096-($-$$) db 0
header:
; The preceding V1 page is intentionally byte-for-byte stable. This second
; independent PIC page uses a separate allocation/header and original CALL.
%define VFRAME 0x128
vision_entry:
    sub rsp, VFRAME
    mov [rsp+0xE0], rax
    mov rax, [rsp+VFRAME+0x28] ; original fifth argument: current sense source
    mov [rsp+0x20], rax       ; forward fifth argument to original calculation
    mov [rsp+0xD8], rax
    mov rax, [rsp+0xE0]
    call [rel vision_header+40] ; 5ED230 always executes, all five args intact
    mov [rsp+0x20], rax
    mov [rsp+0x28], rcx
    mov [rsp+0x30], rdx
    mov [rsp+0x38], r8
    mov [rsp+0x40], r9
    mov [rsp+0x48], r10
    mov [rsp+0x50], r11
    movdqu [rsp+0x60], xmm0
    movdqu [rsp+0x70], xmm1
    movdqu [rsp+0x80], xmm2
    movdqu [rsp+0x90], xmm3
    movdqu [rsp+0xA0], xmm4
    movdqu [rsp+0xB0], xmm5
    mov [rsp+0xE0], rsi
    mov [rsp+0xE8], rdi
    mov dword [rsp+0xF0], 0
    mov rsi, [rsp+0xD8]
    lea r10, [rel vision_header]
    lock inc qword [r10+288]
    mov r11, [r10+64]
    test r11, 1
    jnz v_fallback
    mov [rsp+SEQUENCE], r11
    mov rax, [r10+72]
    test rax, rax
    jz v_fallback
    mov [rsp+DEADLINE], rax
    ; Reject other sources before dereferencing the published character.
    mov edi, 1
    cmp rsi, [r10+88]
    je v_candidate
    inc edi
    cmp rsi, [r10+264]
    jne v_fallback
    test rsi, rsi
    jz v_fallback
v_candidate:
    mov r9, [r10+80]
    test r9, r9
    jz v_fallback
    mov rax, [r10+208]
    cmp [r9], rax
    jne v_fallback
    mov rax, [r10+224]
    mov rax, [rax]
    test rax, rax
    jz v_fallback
    cmp dword [rax+0x48], 7
    jne v_fallback
    cmp byte [rax+0x7C], 0
    je v_fallback
    mov rax, [r10+48]
    mov rax, [rax]
    test rax, rax
    jz v_fallback
    mov rax, [rax+0x60]
    test rax, rax
    jz v_fallback
    cmp [rax+0x170], r9
    jne v_fallback
    mov rax, [r9+0x2400]
    sub rax, 0x10
    cmp rax, [r10+112]
    jne v_fallback
    mov rdx, [r10+216]
    cmp [rax], rdx
    jne v_fallback
    cmp [rax+0x68], r9
    jne v_fallback
    mov eax, [r9+0x2098]
    cmp rax, [r10+96]
    jne v_fallback
    test ax, ax
    jz v_fallback
    mov r8d, eax
    shr eax, 16
    mov rdx, [r10+56]
    mov rdx, [rdx]
    test rdx, rdx
    jz v_fallback
    mov rdx, [rdx+0x20290]
    cmp rdx, [r10+104]
    jne v_fallback
    cmp eax, [rdx+0x120]
    jae v_fallback
    mov rcx, [rdx+8]
    cmp rcx, [r10+120]
    jne v_fallback
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne v_fallback
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, [r10+88]
    jne v_fallback
    cmp dword [rax+0x170], 1
    jne v_fallback
    test byte [rax+0x17C], 1
    jz v_fallback
    cmp [rax+0xB8], r9
    jne v_fallback
    mov r8, [r10+96]
    shr r8d, 16
    cmp [rax+0x174], r8w
    jne v_fallback
    cmp edi, 1
    je v_identity_ok
    ; A vehicle must still be driven by this local handle and resolve back
    ; through its own generation-map entry. No fixed vehicle or slot ID.
    cmp dword [rsi+0x170], 2
    jne v_fallback
    test byte [rsi+0x17C], 1
    jz v_fallback
    mov r8d, [rsi+0x54]
    cmp r8, [r10+96]
    jne v_fallback
    mov r9, [r10+256]
    test r9, r9
    jz v_fallback
    mov r8, [r10+232]
    cmp [r9], r8
    jne v_fallback
    lea r8, [r9+8]
    cmp [rsi+0x40], r8
    jne v_fallback
    mov r8, [r10+240]
    cmp [r9+8], r8
    jne v_fallback
    mov r8d, [r9+0x5020]
    cmp r8, [r10+280]
    jne v_fallback
    cmp [rax+0x120], r8d
    jne v_fallback
    mov eax, [r9+0x4A28]
    cmp rax, [r10+272]
    jne v_fallback
    test ax, ax
    jz v_fallback
    mov r8d, eax
    shr eax, 16
    cmp [rsi+0x174], ax
    jne v_fallback
    cmp eax, [rdx+0x120]
    jae v_fallback
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne v_fallback
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, rsi
    jne v_fallback
v_identity_ok:
    cmp r11, [r10+64]
    jne v_fallback
    cmp dword [rsp+0xF0], 0
    jne v_final
    mov dword [rsp+0xF0], 1
    lea rcx, [rsp+QPC]
    mov rax, [r10+32]
    call [rax]
    test eax, eax
    jz v_fallback
    mov rax, [rsp+QPC]
    cmp rax, [rsp+DEADLINE]
    jae v_fallback
    lea r10, [rel vision_header]
    mov r11, [rsp+SEQUENCE]
    cmp r11, [r10+64]
    jne v_fallback
    ; Validate the entire canonical and generation-map binding again after
    ; QPC, including world/player/vehicle replacement during that call.
    jmp v_candidate
v_final:
    cmp edi, 1
    jne v_vehicle_count
    lock inc qword [r10+296]
    jmp v_filter
v_vehicle_count:
    lock inc qword [r10+304]
v_filter:
    mov eax, [rsp+0x60]
    mov [r10+320], eax
    mov dword [r10+324], 0
    mov [r10+328], rsi
    mov rax, [rsp+QPC]
    mov [r10+336], rax
    mov [r10+344], r11
    mov dword [rsp+0x60], 0  ; only the scalar visual return; upper96 intact
    jmp v_restore
v_fallback:
    lea r10, [rel vision_header]
    lock inc qword [r10+312]
v_restore:
    movdqu xmm0, [rsp+0x60]
    movdqu xmm1, [rsp+0x70]
    movdqu xmm2, [rsp+0x80]
    movdqu xmm3, [rsp+0x90]
    movdqu xmm4, [rsp+0xA0]
    movdqu xmm5, [rsp+0xB0]
    mov rax, [rsp+0x20]
    mov rcx, [rsp+0x28]
    mov rdx, [rsp+0x30]
    mov r8, [rsp+0x38]
    mov r9, [rsp+0x40]
    mov r10, [rsp+0x48]
    mov r11, [rsp+0x50]
    mov rsi, [rsp+0xE0]
    mov rdi, [rsp+0xE8]
    add rsp, VFRAME
    ret
times 8192-($-$$) db 0
vision_header:
; Scent uses its own CALL/header; both preceding pages remain byte-stable.
%define SFRAME 0x120
scent_entry:
    pushfq
    sub rsp, SFRAME
    mov [rsp+0x100], rax
    mov rax, [rsp+SFRAME+0x30] ; original arg5: receiver XYZ
    mov [rsp+0x20], rax
    mov rax, [rsp+SFRAME+0x38] ; original arg6: receiver sense data
    mov [rsp+0x28], rax
    mov rax, [rsp+SFRAME+0x40] ; original arg7: current scent source
    mov [rsp+0x30], rax
    mov [rsp+0xD8], rax
    mov rax, [rsp+0x100]
    push qword [rsp+SFRAME]
    popfq
    call [rel scent_header+40] ; original scent calculation always executes
    pushfq
    pop qword [rsp+0xF8]
    mov [rsp+0x20], rax
    mov [rsp+0x28], rcx
    mov [rsp+0x30], rdx
    mov [rsp+0x38], r8
    mov [rsp+0x40], r9
    mov [rsp+0x48], r10
    mov [rsp+0x50], r11
    movdqu [rsp+0x60], xmm0
    movdqu [rsp+0x70], xmm1
    movdqu [rsp+0x80], xmm2
    movdqu [rsp+0x90], xmm3
    movdqu [rsp+0xA0], xmm4
    movdqu [rsp+0xB0], xmm5
    mov [rsp+0xE0], rsi
    mov [rsp+0xE8], rdi
    mov dword [rsp+0xF0], 0
    mov rsi, [rsp+0xD8]
    lea r10, [rel scent_header]
    lock inc qword [r10+256]
    mov r11, [r10+64]
    test r11, 1
    jnz s_fallback
    mov [rsp+SEQUENCE], r11
    mov rax, [r10+72]
    test rax, rax
    jz s_fallback
    mov [rsp+DEADLINE], rax
    cmp rsi, [r10+88]
    jne s_fallback
s_candidate:
    mov r9, [r10+80]
    test r9, r9
    jz s_fallback
    mov rax, [r10+208]
    cmp [r9], rax
    jne s_fallback
    mov rax, [r10+224]
    mov rax, [rax]
    test rax, rax
    jz s_fallback
    cmp dword [rax+0x48], 7
    jne s_fallback
    cmp byte [rax+0x7C], 0
    je s_fallback
    mov rax, [r10+48]
    mov rax, [rax]
    test rax, rax
    jz s_fallback
    mov rax, [rax+0x60]
    test rax, rax
    jz s_fallback
    cmp [rax+0x170], r9
    jne s_fallback
    mov rax, [r9+0x2400]
    sub rax, 0x10
    cmp rax, [r10+112]
    jne s_fallback
    mov rdx, [r10+216]
    cmp [rax], rdx
    jne s_fallback
    cmp [rax+0x68], r9
    jne s_fallback
    mov eax, [r9+0x2098]
    cmp rax, [r10+96]
    jne s_fallback
    test ax, ax
    jz s_fallback
    mov r8d, eax
    shr eax, 16
    mov rdx, [r10+56]
    mov rdx, [rdx]
    test rdx, rdx
    jz s_fallback
    mov rdx, [rdx+0x20290]
    cmp rdx, [r10+104]
    jne s_fallback
    cmp eax, [rdx+0x120]
    jae s_fallback
    mov rcx, [rdx+8]
    cmp rcx, [r10+120]
    jne s_fallback
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne s_fallback
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, [r10+88]
    jne s_fallback
    cmp dword [rax+0x170], 1
    jne s_fallback
    test byte [rax+0x17C], 1
    jz s_fallback
    cmp [rax+0xB8], r9
    jne s_fallback
    mov r8, [r10+96]
    shr r8d, 16
    cmp [rax+0x174], r8w
    jne s_fallback
    cmp r11, [r10+64]
    jne s_fallback
    cmp dword [rsp+0xF0], 0
    jne s_filter
    mov dword [rsp+0xF0], 1
    lea rcx, [rsp+QPC]
    mov rax, [r10+32]
    call [rax]
    test eax, eax
    jz s_fallback
    mov rax, [rsp+QPC]
    cmp rax, [rsp+DEADLINE]
    jae s_fallback
    lea r10, [rel scent_header]
    mov r11, [rsp+SEQUENCE]
    cmp r11, [r10+64]
    jne s_fallback
    jmp s_candidate ; complete world/local/generation binding after QPC
s_filter:
    lock inc qword [r10+264]
    mov eax, [rsp+0x60]
    mov [r10+288], eax
    mov dword [r10+292], 0
    mov [r10+296], rsi
    mov rax, [rsp+QPC]
    mov [r10+304], rax
    mov [r10+312], r11
    mov dword [rsp+0x60], 0 ; only scent scalar, upper96 bits unchanged
    jmp s_restore
s_fallback:
    lea r10, [rel scent_header]
    lock inc qword [r10+280]
s_restore:
    movdqu xmm0, [rsp+0x60]
    movdqu xmm1, [rsp+0x70]
    movdqu xmm2, [rsp+0x80]
    movdqu xmm3, [rsp+0x90]
    movdqu xmm4, [rsp+0xA0]
    movdqu xmm5, [rsp+0xB0]
    mov rax, [rsp+0x20]
    mov rcx, [rsp+0x28]
    mov rdx, [rsp+0x30]
    mov r8, [rsp+0x38]
    mov r9, [rsp+0x40]
    mov r10, [rsp+0x48]
    mov r11, [rsp+0x50]
    mov rsi, [rsp+0xE0]
    mov rdi, [rsp+0xE8]
    push qword [rsp+0xF8]
    popfq
    lea rsp, [rsp+SFRAME+8]
    ret

times 12288-($-$$) db 0
scent_header:
