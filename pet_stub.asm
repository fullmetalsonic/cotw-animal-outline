; Flat x64 PIC. Only the local dog's HideAllClues getter return is overridden.
BITS 64
ORG 0
%define FRAME 0x108
entry:
    sub rsp, FRAME
    mov [rsp+0xD8], rcx
    mov [rsp+0xE0], edx
    call [rel header+40]       ; native getter always runs with original args
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
    mov dword [rsp+0xE8], 0
    lea r10, [rel header]
    lock inc qword [r10+320]
    cmp dword [rsp+0xE0], 0xC4
    jne fallback
    mov rax, [r10+232]
    mov rax, [rax]
    cmp [rsp+0xD8], rax
    jne fallback
    mov r11, [r10+64]
    test r11, 1
    jnz fallback
    mov [rsp+0xC0], r11
    mov rax, [r10+72]
    test rax, rax
    jz fallback
    mov [rsp+0xC8], rax
validate:
    cmp rbx, [r10+264]
    jne fallback
    mov r9, [r10+256]         ; dog character, closed back to input component
    test r9, r9
    jz fallback
    cmp [rbx+0x18], r9       ; engine-owned pointer before published dereference
    jne fallback
    mov rax, [r10+208]
    cmp [r9], rax
    jne fallback
    cmp [r9+0x2AD8], rbx
    jne fallback
    mov eax, [r9+0x2098]
    cmp rax, [r10+280]
    jne fallback
    mov rax, [rbx+0xB0]
    cmp rax, [r10+296]
    jne fallback
    test rax, rax
    jz fallback
    movzx ecx, byte [rax]
    cmp rcx, [r10+288]
    jne fallback
    cmp byte [rax+1], 0
    je fallback
    ; Live world and canonical local-player identity/owner-ID.
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
    cmp rax, [r10+120]
    jne fallback
    test rax, rax
    jz fallback
    movzx ecx, byte [rax+0x148]
    cmp rcx, [r10+288]
    jne fallback
    mov r9, [r10+80]
    cmp [rax+0x170], r9
    jne fallback
    test r9, r9
    jz fallback
    mov rax, [r10+208]
    cmp [r9], rax
    jne fallback
    mov rax, [r9+0x2400]
    sub rax, 0x10
    cmp rax, [r10+88]
    jne fallback
    mov rdx, [r10+216]
    cmp [rax], rdx
    jne fallback
    cmp [rax+0x68], r9
    jne fallback
    mov rdx, [r9+0x2AD0]
    cmp rdx, [r10+312]
    jne fallback
    test rdx, rdx
    jz fallback
    cmp [rdx+0x10], rax
    jne fallback
    mov eax, [r9+0x2098]
    cmp rax, [r10+96]
    jne fallback
    test ax, ax
    jz fallback
    mov r8d, eax
    shr eax, 16
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
    cmp rcx, [r10+112]
    jne fallback
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne fallback
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, [r10+304]
    jne fallback
    cmp dword [rax+0x170], 1
    jne fallback
    test byte [rax+0x17C], 1
    jz fallback
    cmp [rax+0xB8], r9
    jne fallback
    mov r8, [r10+96]
    shr r8d, 16
    cmp [rax+0x174], r8w
    jne fallback
    ; Dog's independent generation-map binding, not a guessed pool slot.
    mov rax, [r10+280]
    test ax, ax
    jz fallback
    mov r8d, eax
    shr eax, 16
    cmp eax, [rdx+0x120]
    jae fallback
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne fallback
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, [r10+272]
    jne fallback
    cmp dword [rax+0x170], 1
    jne fallback
    test byte [rax+0x17C], 1
    jz fallback
    mov r9, [r10+256]
    cmp [rax+0xB8], r9
    jne fallback
    mov r8, [r10+280]
    shr r8d, 16
    cmp [rax+0x174], r8w
    jne fallback
    cmp r11, [r10+64]
    jne fallback
    cmp dword [rsp+0xE8], 0
    jne filter
    mov dword [rsp+0xE8], 1
    lea rcx, [rsp+0xD0]
    mov rax, [r10+32]
    call [rax]
    test eax, eax
    jz fallback
    mov rax, [rsp+0xD0]
    cmp rax, [rsp+0xC8]
    jae fallback
    lea r10, [rel header]
    mov r11, [rsp+0xC0]
    cmp r11, [r10+64]
    jne fallback
    jmp validate               ; full identity recheck after the QPC call
filter:
    lock inc qword [r10+328]
    mov eax, [rsp+0x20]
    mov [r10+344], rax
    mov qword [r10+352], 0
    mov [r10+360], rbx
    mov rax, [rsp+0xD0]
    mov [r10+368], rax
    mov [r10+376], r11
    mov dword [rsp+0x20], 0   ; only EAX, the dog-local HideAllClues result
    jmp restore
fallback:
    lea r10, [rel header]
    lock inc qword [r10+336]
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
    ret
times 4096-($-$$) db 0
header:
