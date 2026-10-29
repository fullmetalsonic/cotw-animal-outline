; Original native broadphase/contact filter runs once. We only remove pairs
; belonging to one generation-bound carried ragdoll in its original world.
pair_entry:
    NATIVE_START 440
    lock inc qword [rel header+STATS+168]
    lea rbx, [rel header+S]
    cmp dword [rbx+PHASE], 0
    je pair_restore
    mov r13, [rsp+0x30]      ; native hknpWorld
    cmp r13, [rbx+WORLD]
    jne pair_restore
    mov r12, [rsp+0x100]     ; count returned by original native filter
    test r12d, r12d
    jle pair_restore
    cmp r12d, 4096
    ja pair_restore
    xor eax, eax
    mov ecx, 1
    lock cmpxchg [rbx+LOCK], ecx
    jne pair_restore
    lea r10, [rel header]
    mov rax, [r10+64]
    test rax, 1
    jnz pair_unlock
    mov [rsp+0x340], rax
    mov rax, [r10+72]
    test rax, rax
    jz pair_unlock
    mov [rsp+0x348], rax
    mov rax, [r10+264]
    cmp rax, [rbx+DOG]
    jne pair_unlock
    mov rax, [r10+320]
    cmp rax, [rbx+JOB]
    jne pair_unlock
    lea rcx, [rsp+0x350]
    mov rax, [r10+32]
    call [rax]
    test eax, eax
    jz pair_unlock
    mov rax, [rsp+0x350]
    cmp rax, [rsp+0x348]
    jae pair_unlock
    call resolve_target
    test rax, rax
    jz pair_unlock
    mov r14, [rsp+0x38]
    mov r15, r14
    ; Backup the original filter's output, so a concurrent OFF/rebind can
    ; restore it exactly instead of publishing a partial filter decision.
    xor edi, edi
    lea r9, [rel pair_backup]
.backup:
    mov rax, [r14+rdi*8]
    mov [r9+rdi*8], rax
    inc edi
    cmp edi, r12d
    jb .backup
    xor edi, edi
.pair:
    mov ecx, [r14]
    call find_carried_body
    mov [rsp+0x330], eax
    mov ecx, [r14+4]
    call find_carried_body
    mov [rsp+0x334], eax
    test eax, eax
    jnz .b_carried
    cmp dword [rsp+0x330], 0
    je .keep
    mov ecx, [r14+4]
    jmp .other
.b_carried:
    cmp dword [rsp+0x330], 0
    jne .keep                ; retain native self/constraint collision policy
    mov ecx, [r14]
.other:
    cmp ecx, [r13+0x28]
    jae .keep
    imul rax, rcx, 0x90
    add rax, [r13+0x20]
    cmp [rax+0x60], ecx
    jne .keep
    test byte [rax+0x40], 1
    jz .obstacle
    mov ecx, [rbx+TERRAIN]
    cmp [rax+0x44], ecx
    jne .obstacle
    mov dword [rbx+FLOOR], 1 ; actual pair with the typed terrain owner group
    jmp .keep
.obstacle:
    cmp dword [rbx+PHASE], 2
    je .next                 ; pending registration preserves ALL collisions
.keep:
    mov rax, [r14]
    mov [r15], rax
    add r15, 8
.next:
    add r14, 8
    inc edi
    cmp edi, r12d
    jb .pair
    mov rax, [rsp+0x340]
    cmp rax, [rel header+64]
    jne .rollback
    mov rax, [rsp+0x348]
    cmp rax, [rel header+72]
    jne .rollback
    sub r15, [rsp+0x38]
    shr r15, 3
    mov [rsp+0x100], r15
    jmp pair_unlock
.rollback:
    mov r14, [rsp+0x38]
    xor edi, edi
    lea r9, [rel pair_backup]
.copy_back:
    mov rax, [r9+rdi*8]
    mov [r14+rdi*8], rax
    inc edi
    cmp edi, r12d
    jb .copy_back
pair_unlock:
    mov dword [rbx+LOCK], 0
pair_restore:
    NATIVE_END

; ECX=native pair body ID. Comparing an ID is not enough: the original target
; generation and this body's shape/userData/motion/mapping must still match.
find_carried_body:
    lea rsi, [rel header+BODY]
    xor r11d, r11d
.search:
    cmp r11d, [rbx+COUNT]
    jae .no
    cmp [rsi], ecx
    je .found
    inc r11d
    add rsi, 32
    jmp .search
.found:
    call checked_body
    test rax, rax
    setne al
    movzx eax, al
    ret
.no:
    xor eax, eax
    ret

 times 20480-($-$$) db 0
speed_entry:
    NATIVE_START 432
    lea rbx, [rel header+S]
    cmp dword [rbx+PHASE], 2
    jne speed_restore
    xor eax, eax
    mov ecx, 1
    lock cmpxchg [rbx+LOCK], ecx
    jne speed_restore
    mov rax, [rsp+0x28]      ; real native Retriever job argument
    cmp rax, [rbx+JOB]
    jne speed_unlock
    mov [rsp+0xE8], rax
    mov dword [rsp+0xF8], 0
    CHECK_BINDING speed_unlock, speed_bound
speed_bound:
    lea rbx, [rel header+S]
    call resolve_target
    test rax, rax
    jz speed_unlock
    mov dword [rsp+0x180], 0x3F800000 ; movement factor only, never actual mass
speed_unlock:
    lea rbx, [rel header+S]
    mov dword [rbx+LOCK], 0
speed_restore:
    NATIVE_END

; Private writable data is outside the RX bundle. One pair reader owns LOCK.
pair_backup equ header+16384
