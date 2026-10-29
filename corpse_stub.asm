; NASM 2.x, flat x64 binary. No imports, absolute code addresses, or assembler
; are needed at runtime. The adjacent RW header is supplied by corpse_outline.
BITS 64
ORG 0

%define FRAME 0x108
%define SAVED_RCX 0x28
%define SAVED_RAX 0x20
%define SEQUENCE 0xE8
%define DEADLINE 0xF0
%define QPC 0xF8

entry:
    ; CALL entry RSP%16=8. Reserve shadow space and preserve volatile values
    ; so the default path is exactly the original reset call, including args.
    sub rsp, FRAME
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
    mov r11, [r10+64]
    test r11, 1
    jnz original
    mov [rsp+SEQUENCE], r11
    mov rax, [r10+72]
    test rax, rax
    jz original
    mov [rsp+DEADLINE], rax
    mov r9, [r10+80]
    test r9, r9
    jz original
    cmp r9, 4096
    ja original
    lea r8, [r10+256]
find:
    cmp [r8], rbx
    jne next
    cmp [r8+8], rcx
    je found
next:
    add r8, 32
    dec r9
    jnz find
    jmp original
found:
    ; RBX is the wrapper already owned by the game's current corpse tick.
    cmp [rbx], rcx
    jne original
    mov rax, [rbx+0x28]
    cmp [r8+16], rax
    jne original
    mov eax, [rbx+0xCC]
    cmp eax, 0xDEADBEEF
    je original
    cmp [r8+24], eax
    jne original
    test byte [rbx+0xD4], 4
    jz original
    cmp byte [rbx+0x25C], 0
    jne original
    mov rax, [r10+104]
    cmp [rcx], rax
    jne original
    cmp word [rcx+0x220], 0
    jne original
    cmp byte [rcx+0x21C], 1
    jne original
    xorps xmm0, xmm0
    ucomiss xmm0, [rbx+0x17C]
    jp original
    jb original
    ; Snapshot RGBA and lease only after a matching, currently valid object.
    movdqu xmm0, [r10+88]
    movdqu [rsp+0xC0], xmm0
    cmp r11, [r10+64]
    jne original
    lea rcx, [rsp+QPC]
    mov rax, [r10+32]
    call [rax]                   ; game's QueryPerformanceCounter IAT
    test eax, eax
    jz original
    mov rax, [rsp+QPC]
    cmp rax, [rsp+DEADLINE]
    jae original
    lea r10, [rel header]
    mov rax, [rsp+SEQUENCE]
    cmp rax, [r10+64]
    jne original
    mov rcx, [rsp+SAVED_RCX]
    mov eax, [rcx+0x1098]
    test eax, eax
    jz original
    cmp eax, 64
    ja original
    ; The engine's common updater receives dt=0. Seed current and target RGBA
    ; identically, so its interpolation retains our color and handles model
    ; packing / bit22 itself. QPC lease, not dt=0, bounds activation lifetime.
    movdqu xmm0, [rsp+0xC0]
    movups [rcx+0x2458], xmm0
    movups [rcx+0x2468], xmm0
    mov dword [rcx+0x2478], 0x3E99999A ; 0.30 s
    mov dword [rcx+0x247C], 0x3DCCCCCD ; 0.10 s
    mov dword [rcx+0x2480], 0x3DCCCCCD
    ; Disable the conflicting native corpse pass on every current model.
    mov r9d, [rcx+0x1098]
    xor r8d, r8d
clear_native:
    cmp r8d, r9d
    jae update
    mov rax, [rcx+r8*8+0x11A0]
    test rax, rax
    jz next_model
    and dword [rax+0xC], 0xFFFFFFBF
next_model:
    inc r8d
    jmp clear_native
update:
    xorps xmm1, xmm1
    call [rel header+48]          ; CCharacter outline update, Win64 ABI
    ; Skip the remaining corpse RGB/bit6 overwrite. These are the original
    ; nonvolatile saves in 8BDDC0, relative to its pre-CALL stack pointer.
    add rsp, FRAME+8              ; discard detour CALL's return address
    movaps xmm8, [rsp+0x90]
    movaps xmm7, [rsp+0xA0]
    mov rsi, [rsp+0xE0]
    mov rbp, [rsp+0xD8]
    jmp [rel header+56]           ; 8BE1AB: RBX restore / stack / RDI / ret

original:
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
    jmp [rel header+40]           ; original reset returns to original caller

times 4096-($-$$) db 0
header:                           ; separate RW page; no code is patched here
