; Eligibility, original pickup, native dog tick, speed and collision filtering.
; No body weight/class/health, reward or save fields are written.
; shortcut: no dynamic unwind registration, matching the existing native hooks.
%define STATS 512
BITS 64
ORG 0
%define FRAME 0x128
%macro SAVE 0
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
    mov [rsp+0xF0], rsi
    mov dword [rsp+0xF8], 0
%endmacro
%macro RESTORE 0
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
    mov rsi, [rsp+0xF0]
    add rsp, FRAME
%endmacro
%macro CHECK_BINDING 2
    lea r10, [rel header]
    mov r11, [r10+64]
    mov [rsp+0xC0], r11
    test r11, 1
    jnz %1
    mov rax, [r10+72]
    test rax, rax
    jz %1
    mov [rsp+0xC8], rax
%%validate:
    mov rax, [rsp+0xE8]       ; engine input job, not a published pointer first
    cmp rax, [r10+320]
    jne %1
    test rax, rax
    jz %1
    mov rdx, [r10+240]
    cmp [rax], rdx
    jne %1
    mov rsi, [rax+0x18]
    cmp rsi, [r10+264]
    jne %1
    mov r9, [r10+256]         ; dog character, closed back to input component
    test r9, r9
    jz %1
    cmp [rsi+0x18], r9       ; engine-owned pointer before published dereference
    jne %1
    mov rax, [r10+208]
    cmp [r9], rax
    jne %1
    cmp [r9+0x2AD8], rsi
    jne %1
    mov eax, [r9+0x2098]
    cmp rax, [r10+280]
    jne %1
    mov rax, [rsi+0xB0]
    cmp rax, [r10+296]
    jne %1
    test rax, rax
    jz %1
    movzx ecx, byte [rax]
    cmp rcx, [r10+288]
    jne %1
    cmp byte [rax+1], 0
    je %1
    ; Live world and canonical local-player identity/owner-ID.
    mov rax, [r10+224]
    mov rax, [rax]
    test rax, rax
    jz %1
    cmp dword [rax+0x48], 7
    jne %1
    cmp byte [rax+0x7C], 0
    je %1
    mov rax, [r10+48]
    mov rax, [rax]
    test rax, rax
    jz %1
    mov rax, [rax+0x60]
    cmp rax, [r10+120]
    jne %1
    test rax, rax
    jz %1
    movzx ecx, byte [rax+0x148]
    cmp rcx, [r10+288]
    jne %1
    mov r9, [r10+80]
    cmp [rax+0x170], r9
    jne %1
    test r9, r9
    jz %1
    mov rax, [r10+208]
    cmp [r9], rax
    jne %1
    mov rax, [r9+0x2400]
    sub rax, 0x10
    cmp rax, [r10+88]
    jne %1
    mov rdx, [r10+216]
    cmp [rax], rdx
    jne %1
    cmp [rax+0x68], r9
    jne %1
    mov rdx, [r9+0x2AD0]
    cmp rdx, [r10+312]
    jne %1
    test rdx, rdx
    jz %1
    cmp [rdx+0x10], rax
    jne %1
    mov eax, [r9+0x2098]
    cmp rax, [r10+96]
    jne %1
    test ax, ax
    jz %1
    mov r8d, eax
    shr eax, 16
    mov rdx, [r10+56]
    mov rdx, [rdx]
    test rdx, rdx
    jz %1
    mov rdx, [rdx+0x20290]
    cmp rdx, [r10+104]
    jne %1
    cmp eax, [rdx+0x120]
    jae %1
    mov rcx, [rdx+8]
    cmp rcx, [r10+112]
    jne %1
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne %1
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, [r10+304]
    jne %1
    cmp dword [rax+0x170], 1
    jne %1
    test byte [rax+0x17C], 1
    jz %1
    cmp [rax+0xB8], r9
    jne %1
    mov r8, [r10+96]
    shr r8d, 16
    cmp [rax+0x174], r8w
    jne %1
    ; Dog's independent generation-map binding, not a guessed pool slot.
    mov rax, [r10+280]
    test ax, ax
    jz %1
    mov r8d, eax
    shr eax, 16
    cmp eax, [rdx+0x120]
    jae %1
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne %1
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp rax, [r10+272]
    jne %1
    cmp dword [rax+0x170], 1
    jne %1
    test byte [rax+0x17C], 1
    jz %1
    mov r9, [r10+256]
    cmp [rax+0xB8], r9
    jne %1
    mov r8, [r10+280]
    shr r8d, 16
    cmp [rax+0x174], r8w
    jne %1
    cmp r11, [r10+64]
    jne %1
    cmp dword [rsp+0xF8], 0
    jne %2
    mov dword [rsp+0xF8], 1
    lea rcx, [rsp+0xD0]
    mov rax, [r10+32]
    call [rax]
    test eax, eax
    jz %1
    mov rax, [rsp+0xD0]
    cmp rax, [rsp+0xC8]
    jae %1
    lea r10, [rel header]
    mov r11, [rsp+0xC0]
    cmp r11, [r10+64]
    jne %1
    jmp %%validate               ; full identity recheck after the QPC call
%endmacro
%macro DEAD_EXTENDED_CLASS 1
    mov rax, [rsp+0xE0]       ; original engine wrapper
    test rax, rax
    jz %1
    mov rdx, [rax+0x28]
    test rdx, rdx
    jz %1
    movzx ecx, byte [rdx+0x61]
    cmp ecx, 2
    jb %1
    cmp ecx, 9
    ja %1
    mov edx, [rax+0x17C]
    mov r8d, edx
    and r8d, 0x7F800000
    cmp r8d, 0x7F800000       ; NaN / either infinity never extend eligibility
    je %1
    test edx, 0x7FFFFFFF
    jz %%dead
    test edx, 0x80000000
    jz %1
%%dead:
    mov [r10+STATS+48], rcx
    mov [r10+STATS+56], rax
    mov rax, [rsp+0xE8]
    mov [r10+STATS+64], rax
%endmacro
entry:
    mov rax, [rdx+0x28]      ; exact original MOV, including its RAX effect
    SAVE
    mov [rsp+0xE0], rdx
    mov [rsp+0xE8], rdi
    lea r10, [rel header]
    lock inc qword [r10+STATS+0]
    cmp byte [rax+0x61], 1   ; class 1 always follows the original comparison
    je gate_default
    CHECK_BINDING gate_default, gate_valid
 gate_valid:
    DEAD_EXTENDED_CLASS gate_default
    lock inc qword [r10+STATS+8]
    mov rax, [rsp+0xD0]
    mov [r10+STATS+120], rax
    mov [r10+STATS+128], r11
    RESTORE
    cmp eax, eax            ; extension affects comparison flags only (ZF=1)
    ret
 gate_default:
    lea r10, [rel header]
    lock inc qword [r10+STATS+16]
    RESTORE
    cmp byte [rax+0x61], 1  ; exact native flags after stack restoration
    ret
 times 4096-($-$$) db 0
%define PICKUP_FRAME 0x500
%macro NATIVE_START 1
    pushfq
    sub rsp, PICKUP_FRAME
    mov [rsp+0x28], rcx
    mov [rsp+0x30], rdx
    mov [rsp+0x38], r8
    mov [rsp+0x40], r9
    push qword [rsp+PICKUP_FRAME]
    popfq
    call [rel header+%1]   ; Original always exactly once, no stack arguments.
    mov [rsp+0x100], rax
    mov [rsp+0x108], rcx
    mov [rsp+0x110], rdx
    mov [rsp+0x118], r8
    mov [rsp+0x120], r9
    mov [rsp+0x128], r10
    mov [rsp+0x130], r11
    mov [rsp+0x138], rbx
    mov [rsp+0x140], rbp
    mov [rsp+0x148], rsi
    mov [rsp+0x150], rdi
    mov [rsp+0x158], r12
    mov [rsp+0x160], r13
    mov [rsp+0x168], r14
    mov [rsp+0x170], r15
    movdqu [rsp+0x180], xmm0
    movdqu [rsp+0x190], xmm1
    movdqu [rsp+0x1A0], xmm2
    movdqu [rsp+0x1B0], xmm3
    movdqu [rsp+0x1C0], xmm4
    movdqu [rsp+0x1D0], xmm5
    movdqu [rsp+0x1E0], xmm6
    movdqu [rsp+0x1F0], xmm7
    movdqu [rsp+0x200], xmm8
    movdqu [rsp+0x210], xmm9
    movdqu [rsp+0x220], xmm10
    movdqu [rsp+0x230], xmm11
    movdqu [rsp+0x240], xmm12
    movdqu [rsp+0x250], xmm13
    movdqu [rsp+0x260], xmm14
    movdqu [rsp+0x270], xmm15
    pushfq
    pop qword [rsp+0x280]
%endmacro
%macro NATIVE_END 0
    movdqu xmm0, [rsp+0x180]
    movdqu xmm1, [rsp+0x190]
    movdqu xmm2, [rsp+0x1A0]
    movdqu xmm3, [rsp+0x1B0]
    movdqu xmm4, [rsp+0x1C0]
    movdqu xmm5, [rsp+0x1D0]
    movdqu xmm6, [rsp+0x1E0]
    movdqu xmm7, [rsp+0x1F0]
    movdqu xmm8, [rsp+0x200]
    movdqu xmm9, [rsp+0x210]
    movdqu xmm10, [rsp+0x220]
    movdqu xmm11, [rsp+0x230]
    movdqu xmm12, [rsp+0x240]
    movdqu xmm13, [rsp+0x250]
    movdqu xmm14, [rsp+0x260]
    movdqu xmm15, [rsp+0x270]
    mov rax, [rsp+0x100]
    mov rcx, [rsp+0x108]
    mov rdx, [rsp+0x110]
    mov r8, [rsp+0x118]
    mov r9, [rsp+0x120]
    mov r10, [rsp+0x128]
    mov r11, [rsp+0x130]
    mov rbx, [rsp+0x138]
    mov rbp, [rsp+0x140]
    mov rsi, [rsp+0x148]
    mov rdi, [rsp+0x150]
    mov r12, [rsp+0x158]
    mov r13, [rsp+0x160]
    mov r14, [rsp+0x168]
    mov r15, [rsp+0x170]
    push qword [rsp+0x280]
    popfq
    lea rsp, [rsp+PICKUP_FRAME+8]
    ret
%endmacro
pickup_entry:
    NATIVE_START 40
    lea r10, [rel header]
    lock inc qword [r10+STATS+24]
    mov rcx, [rsp+0x28]
    cmp byte [rcx], 1
    jne pickup_default
    mov r9, [rsp+0x30]        ; Native-held local dog before any published job dereference.
    cmp r9, [r10+256]
    jne pickup_default
    mov rsi, [r9+0x2AD8]
    cmp rsi, [r10+264]
    jne pickup_default
    test rsi, rsi
    jz pickup_default
    mov rax, [rsi+0xC8]
    test rax, rax
    jz pickup_default
    mov r8, [rsi+0xD0]
    sub r8, rax
    jz pickup_default
    cmp r8, 256
    ja pickup_default
    test r8, 7
    jnz pickup_default
    add r8, rax
    mov rdx, [r10+320]
find_job:
    cmp [rax], rdx
    je pickup_job
    add rax, 8
    cmp rax, r8
    jb find_job
    jmp pickup_default
pickup_job:
    mov [rsp+0xE8], rdx
    mov r9, [rsp+0x38]
    mov rax, [r10+208]
    cmp [r9], rax
    jne pickup_default
    mov rax, [r9+0x2AC8]
    test rax, rax
    jz pickup_default
    mov rax, [rax+0x168]
    test rax, rax
    jz pickup_default
    mov [rsp+0xE0], rax
    mov eax, [r9+0x2098]
    mov [rsp+0x2D0], eax
    mov dword [rsp+0xF8], 0
    CHECK_BINDING pickup_default, pickup_valid
pickup_valid:
    DEAD_EXTENDED_CLASS pickup_default
    mov r9, [rsp+0x38]
    mov rax, [rsp+0xE0]
    cmp [rax], r9
    jne pickup_default
    mov rdx, [r9+0x2AC8]
    test rdx, rdx
    jz pickup_default
    cmp [rdx+0x168], rax
    jne pickup_default
    mov eax, [r9+0x2098]
    cmp eax, [rsp+0x2D0]
    jne pickup_default
    test ax, ax
    jz pickup_default
    mov r8d, eax
    shr eax, 16
    mov rdx, [r10+104]
    cmp eax, [rdx+0x120]
    jae pickup_default
    mov rcx, [r10+112]
    mov eax, [rcx+rax*4]
    cmp ax, r8w
    jne pickup_default
    shr eax, 16
    imul rax, rax, 0x180
    add rax, [rdx]
    cmp [rax+0xB8], r9
    jne pickup_default
    cmp dword [rax+0x170], 1
    jne pickup_default
    test byte [rax+0x17C], 1
    jz pickup_default
    shr r8d, 16
    cmp [rax+0x174], r8w
    jne pickup_default
    mov rax, [r9+8]
    cmp rax, [r10+344]
    jne pickup_default
    mov rcx, [r10+248]
    cmp [rax+0x98], rcx
    jne pickup_default
    mov rax, [r9+0x1AD0]
    test rax, rax
    jz pickup_default
    cmp qword [rax+0xC0], 0
    je pickup_default
    mov rax, [r9+0x1F20]
    test rax, rax
    jz pickup_default
    mov [rsp+0x2D8], rax
    cmp qword [rax+0x78], 0
    je pickup_default
    cmp qword [rax+0x88], 0
    je pickup_default
    mov rax, [rax+0x10]
    test rax, rax
    jz pickup_default
    cmp qword [rax+0x48], 0
    je pickup_default
    mov rax, [rax+0x40]
    test rax, rax
    jz pickup_default
    mov eax, [rax+0x30]
    test eax, eax
    jz pickup_default
    cmp eax, 256
    ja pickup_default
    mov r12, [rsp+0x38]
    mov r13, [rsp+0x30]
    mov r14, [rsp+0xE8]
    mov r15, [rsp+0xE0]
    mov eax, [r15+0x19C]
    mov [r10+STATS+72], eax
    mov [r10+STATS+76], eax
    mov [r10+STATS+112], r12
    mov rax, [rsp+0xD0]
    call register_carry
    test eax, eax
    jz pickup_default
    lea r10, [rel header]
    lock inc qword [r10+STATS+32]
    jmp pickup_restore
pickup_default:
    lea r10, [rel header]
    lock inc qword [r10+STATS+40]
pickup_restore:
    NATIVE_END
 times 8192-($-$$) db 0
%include "hellhound_carry.asm"
 times 16384-($-$$) db 0
%include "hellhound_filter.asm"
 times 24576-($-$$) db 0
header:
