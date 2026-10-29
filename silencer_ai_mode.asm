; Leased local-source sound calculation: replace only the weapon-profile argument.
BITS 64
ORG 0
%define FRAME 0x110
entry_fire:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov qword [rsp+0xE0], 0
    jmp filter_entry
times 64-($-$$) db 0xCC
entry_impact:
    pushfq
    sub rsp, FRAME
    mov [rsp+0x20], rax
    mov qword [rsp+0xE0], 1
filter_entry:
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
    mov qword [rsp+0xF0], 0  ; second validation pass follows the single QPC call
    lea r10, [rel header]
    lock inc qword [r10+256]
    mov rax, [r10+64]
    test rax, 1
    jnz fallback
    mov [rsp+0xC0], rax
    mov rax, [r10+72]
    test rax, rax
    jz fallback
    mov [rsp+0xC8], rax
validate_binding:
    mov rcx, [rsp+0x28]
    cmp rcx, [r10+96]
    jne fallback
    cmp ebx, [r10+88]
    jne fallback
    mov rax, [r10+56]
    mov rax, [rax]
    test rax, rax
    jz fallback
    cmp [rax+0x220], rcx
    jne fallback
    ; Confirm the cached profile is still reachable in the current native tree.
    mov r9, [rcx+0x388]
    test r9, r9
    jz fallback
    mov r11, [r9+8]
    mov edx, 64
find_current_bow:
    test r11, r11
    jz fallback
    cmp byte [r11+0x19], 0
    jne fallback
    cmp dword [r11+0x1C], 0xBD9568A5
    je current_bow_found
    ja current_bow_left
    mov r11, [r11+0x10]
    jmp current_bow_next
current_bow_left:
    mov r11, [r11]
current_bow_next:
    dec edx
    jnz find_current_bow
    jmp fallback
current_bow_found:
    cmp r11, [r10+104]
    jne fallback
    mov r9, r11
    cmp byte [r9+0x19], 0
    jne fallback
    cmp dword [r9+0x1C], 0xBD9568A5
    jne fallback
    cmp dword [r9+0x20], 0x42960000 ; fire zero distance 75
    jne fallback
    cmp dword [r9+0x24], 0x41200000 ; fire one distance 10
    jne fallback
    cmp dword [r9+0x28], 0x40000000 ; fire score 2
    jne fallback
    cmp dword [r9+0x2C], 0x42480000 ; impact zero distance 50
    jne fallback
    cmp dword [r9+0x30], 0x41C80000 ; impact one distance 25
    jne fallback
    cmp dword [r9+0x34], 0x3F800000 ; impact score 1
    jne fallback
    cmp dword [r9+0x38], 0x437A0000 ; projectile-hit-animal score 250
    jne fallback
    mov r9, [r10+112]
    mov r9, [r9]
    test r9, r9
    jz fallback
    mov r9, [r9+0x60]
    test r9, r9
    jz fallback
    mov r9, [r9+0x170]
    cmp r9, [r10+80]
    jne fallback
    mov rax, [r10+120]
    cmp [r9], rax
    jne fallback
    mov eax, [r9+0x2098]
    cmp rax, [r10+88]
    jne fallback
    mov rax, [r9+0x2400]
    sub rax, 0x10
    cmp rax, [r10+144]
    jne fallback
    mov rdx, [r10+128]
    cmp [rax], rdx
    jne fallback
    cmp [rax+0x68], r9
    jne fallback
    cmp qword [rsp+0xF0], 1
    je apply_profile
    mov r8, [rsp+0x38]
    lea r11, [rel weapon_hashes]
    mov ecx, 137
find_weapon:
    cmp r8d, [r11]
    je matched
    add r11, 4
    loop find_weapon
    jmp fallback
matched:
    lea rcx, [rsp+0xD0]
    mov rax, [r10+32]
    call [rax]
    test eax, eax
    jz fallback
    lea r10, [rel header]
    mov rax, [rsp+0xD0]
    cmp rax, [rsp+0xC8]
    jae fallback
    mov rax, [rsp+0xC0]
    cmp rax, [r10+64]
    jne fallback
    mov qword [rsp+0xF0], 1
    jmp validate_binding
apply_profile:
    mov r9, [rsp+0xE0]
    lock inc qword [r10+r9*8+264]
    mov rax, [rsp+0x38]
    mov [r10+288], rax
    mov [r10+296], rbx
    mov rax, [rsp+0xD0]
    mov [r10+304], rax
    mov dword [rsp+0x38], 0xBD9568A5 ; only the calculation argument changes
    mov dword [rsp+0x3C], 0
    jmp restore
fallback:
    lea r10, [rel header]
    lock inc qword [r10+280]
restore:
    mov rax, [rsp+0xE0]
    lea r10, [rel header]
    mov rax, [r10+rax*8+40]
    mov [rsp+0xE8], rax
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
    push qword [rsp+FRAME]
    popfq
    lea rsp, [rsp+FRAME+8]
    ; Load the selected target without changing registers or returned state.
    jmp [rsp-FRAME-8+0xE8]
times 4096-($-$$) db 0
weapon_hashes:
    incbin "silencer_ai_weapon_hashes.bin"
times 8192-($-$$) db 0
header:
