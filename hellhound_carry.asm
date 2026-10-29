; Included by hellhound_stub.asm. All helpers execute on the original dog tick.
; Pair filtering is read-only on game objects; no persistent collision masks.
%define STATS 512
%define S 1024
%define BODY 2048
%define PHASE 0
%define LOCK 4
%define HANDLE 8
%define DOG_HANDLE 12
%define TARGET 16
%define DOG_CHAR 24
%define DOG 32
%define JOB 40
%define WRAPPER 48
%define RAG 56
%define DEF 64
%define SKEL 72
%define WORLD 80
%define ARRAY 88
%define COUNT 96
%define HEAD 100
%define LAST_TIME 104
%define LAST_ANCHOR 112
%define FLOOR 124
%define START_TIME 136
%define REASON 144
%define TERRAIN 148
%define ROOT_BONE 152
%define ROOT_OFFSET 160
%define HAVE_ANCHOR 176
%define ANCHOR_RANK 180
%define CANCEL_DETAIL 184
%define HEAD_DISTANCE_SQUARED 188
%define ROOT_POSE 192

    jmp tick_entry

; Caller holds LOCK. Resolve a weak entity handle through the CURRENT pool
; before touching TARGET, then close wrapper/ragdoll/world identity as well.
; RBX=state, result RAX=target or0. Only volatile registers are clobbered.
resolve_target:
    mov rax, [rel header+224]
    mov rax, [rax]
    test rax, rax
    jz .no
    cmp dword [rax+0x48], 7
    jne .no
    mov rax, [rel header+56]
    mov rax, [rax]
    test rax, rax
    jz .no
    mov rdx, [rax+0x20290]
    test rdx, rdx
    jz .no
    mov r8d, [rbx+HANDLE]
    test r8w, r8w
    jz .no
    mov eax, r8d
    shr eax, 16
    cmp eax, [rdx+0x120]
    jae .no
    mov rcx, [rdx+8]
    test rcx, rcx
    jz .no
    mov ecx, [rcx+rax*4]
    cmp cx, r8w
    jne .no
    shr ecx, 16
    imul rcx, rcx, 0x180
    add rcx, [rdx]
    cmp dword [rcx+0x170], 1
    jne .no
    test byte [rcx+0x17C], 1
    jz .no
    shr r8d, 16
    cmp [rcx+0x174], r8w
    jne .no
    mov rax, [rcx+0xB8]
    cmp rax, [rbx+TARGET]
    jne .no
    test rax, rax
    jz .no
    mov rcx, [rel header+208]
    cmp [rax], rcx
    jne .no
    mov ecx, [rbx+HANDLE]
    cmp [rax+0x2098], ecx
    jne .no
    mov rcx, [rax+0x2AC8]
    test rcx, rcx
    jz .no
    mov rcx, [rcx+0x168]
    cmp rcx, [rbx+WRAPPER]
    jne .no
    test rcx, rcx
    jz .no
    cmp [rcx], rax
    jne .no
    mov edx, [rcx+0x17C]
    and edx, 0x7FFFFFFF
    cmp edx, 0x7F800000
    jae .no
    test edx, edx
    jz .dead
    test byte [rcx+0x17F], 0x80
    jz .no
.dead:
    mov rcx, [rcx+0x28]
    test rcx, rcx
    jz .no
    movzx edx, byte [rcx+0x61]
    sub edx, 2
    cmp edx, 7
    ja .no
    mov rcx, [rax+0x1F20]
    cmp rcx, [rbx+RAG]
    jne .no
    test rcx, rcx
    jz .no
    mov rdx, [rcx+0x10]
    cmp rdx, [rbx+DEF]
    jne .no
    mov r8, [rdx+0x40]
    cmp r8, [rbx+SKEL]
    jne .no
    mov r9d, [r8+0x30]
    dec r9d
    cmp r9d, 255
    ja .no
    mov rdx, [rcx+8]
    cmp rdx, [rbx+WORLD]
    jne .no
    mov rcx, [rdx+0x20]
    cmp rcx, [rbx+ARRAY]
    jne .no
    mov rcx, [rel header+480]
    mov rcx, [rcx]
    test rcx, rcx
    jz .no
    cmp [rcx+0x30], rdx
    jne .no
    cmp dword [rbx+PHASE], 3
    je .resolved             ; rejected pickup needs entity cleanup, no terrain
    mov rcx, [rcx+0x1A078]
    test rcx, rcx
    jz .no
    mov rdx, [rel header+456]
    cmp [rcx], rdx
    jne .no
    mov edx, [rcx+0x38]
    cmp edx, [rbx+TERRAIN]
    jne .no
.resolved:
    ret
.no:
    xor eax, eax
    ret

; RSI=private body record. Def->bone mapping AND current body properties must
; still agree. Body IDs alone have no generation bits in this executable.
checked_body:
    mov rdx, [rbx+WORLD]
    mov eax, [rsi]
    cmp eax, [rdx+0x28]
    jae .no
    imul rax, rax, 0x90
    add rax, [rdx+0x20]
    mov ecx, [rsi]
    cmp [rax+0x60], ecx
    jne .no
    mov rdx, [rsi+8]
    cmp [rax+0x48], rdx
    jne .no
    mov rdx, [rsi+16]
    cmp [rax+0x88], rdx
    jne .no
    mov edx, [rsi+24]
    cmp [rax+0x68], edx
    jne .no
    mov rdx, [rbx+DEF]
    mov r8, [rdx+0x48]
    mov ecx, [rsi+4]
    movsxd rcx, dword [r8+rcx*4]
    cmp ecx, 256
    jae .no
    mov r8, [rdx+0x20]
    mov ecx, [r8+rcx*4]
    cmp ecx, [rsi]
    jne .no
    ret
.no:
    xor eax, eax
    ret

; R12 target,R13 dogchar,R14 job,R15 wrapper,RAX qpc. Native pickup already
; holds both actors. No physics or character pose is changed by registration.
register_carry:
    sub rsp, 0x28
    mov [rsp+0x20], rax
    lea rbx, [rel header+S]
    xor eax, eax
    mov ecx, 1
    lock cmpxchg [rbx+LOCK], ecx
    jne .busy
    cmp dword [rbx+PHASE], 0
    jne .unlock
    mov dword [rbx+REASON], 7 ; no verified terrain owner/group
    mov [rbx+TARGET], r12
    mov [rbx+DOG_CHAR], r13
    mov [rbx+JOB], r14
    mov [rbx+WRAPPER], r15
    mov eax, [r12+0x2098]
    mov [rbx+HANDLE], eax
    mov eax, [r13+0x2098]
    mov [rbx+DOG_HANDLE], eax
    mov rax, [r13+0x2AD8]
    mov [rbx+DOG], rax
    mov rax, [r12+0x1F20]
    mov [rbx+RAG], rax
    mov rcx, [rax+0x10]
    mov [rbx+DEF], rcx
    mov rdx, [rcx+0x40]
    mov [rbx+SKEL], rdx
    mov rax, [rax+8]
    test rax, rax
    jz .unlock
    mov [rbx+WORLD], rax
    mov rax, [rax+0x20]
    test rax, rax
    jz .unlock
    mov [rbx+ARRAY], rax
    mov dword [rbx+COUNT], 0
    mov dword [rbx+PHASE], 3 ; cleanup after original caller publishes its ID
    mov rax, [rel header+480]
    mov rax, [rax]
    test rax, rax
    jz .unlock
    mov rcx, [rbx+WORLD]
    cmp [rax+0x30], rcx
    jne .unlock
    mov rax, [rax+0x1A078]
    test rax, rax
    jz .unlock
    mov rcx, [rel header+456]
    cmp [rax], rcx
    jne .unlock
    mov eax, [rax+0x38]
    mov ecx, eax
    and ecx, 31
    cmp ecx, 3
    jne .unlock
    cmp eax, 0x10000
    jb .unlock
    mov [rbx+TERRAIN], eax
    mov dword [rbx+REASON], 4 ; unsupported/missing physical head
    mov dword [rbx+HEAD], -1
    mov dword [rbx+ROOT_BONE], -1
    mov dword [rbx+COUNT], 0
    mov dword [rbx+FLOOR], 0
    mov dword [rbx+HAVE_ANCHOR], 0
    mov dword [rbx+ANCHOR_RANK], 0
    mov dword [rbx+CANCEL_DETAIL], 0
    mov dword [rbx+HEAD_DISTANCE_SQUARED], 0
    mov qword [rel header+STATS+200], 0
    mov qword [rel header+STATS+208], 0
    pxor xmm0, xmm0
    movups [rel header+STATS+224], xmm0
    movups [rel header+STATS+240], xmm0
    movups [rel header+STATS+256], xmm0
    movups [rel header+STATS+272], xmm0
    xor edi, edi
    lea rsi, [rel header+BODY]
.bone:
    mov rax, [rbx+SKEL]
    cmp edi, [rax+0x30]
    jae .bones_done
    cmp edi, 256
    jae .unlock
    mov rdx, [rbx+DEF]
    mov rcx, [rdx+0x48]
    movsxd rcx, dword [rcx+rdi*4]
    cmp ecx, 256
    jae .next
    mov rdx, [rdx+0x20]
    mov ecx, [rdx+rcx*4]
    mov rdx, [rbx+WORLD]
    cmp ecx, [rdx+0x28]
    jae .unlock
    imul r8, rcx, 0x90
    add r8, [rdx+0x20]
    cmp [r8+0x60], ecx
    jne .unlock
    test byte [r8+0x40], 2
    jz .unlock
    cmp qword [r8+0x48], 0
    je .unlock
    mov [rsi], ecx
    mov [rsi+4], edi
    mov rcx, [r8+0x48]
    mov [rsi+8], rcx
    mov rcx, [r8+0x88]
    mov [rsi+16], rcx
    mov ecx, [r8+0x68]
    mov [rsi+24], ecx
    cmp dword [rbx+ROOT_BONE], -1
    jne .name
    mov [rbx+ROOT_BONE], edi
.name:
    mov rax, [rax+0x28]
    test rax, rax
    jz .unlock
    mov ecx, edi
    shl rcx, 4
    mov rax, [rax+rcx]
    and rax, -2
    test rax, rax
    jz .append
    ; Match the final anatomical token, independent of rig/species namespace.
    mov rdx, rax
    xor ecx, ecx
.name_scan:
    cmp ecx, 127
    jae .append
    movzx r8d, byte [rax+rcx]
    test r8b, r8b
    jz .name_end
    cmp r8b, '_'
    je .separator
    cmp r8b, ':'
    je .separator
    cmp r8b, '|'
    je .separator
    cmp r8b, '/'
    je .separator
    cmp r8b, '.'
    jne .name_next
.separator:
    lea rdx, [rax+rcx+1]
.name_next:
    inc ecx
    jmp .name_scan
.name_end:
    mov rax, rdx
.head_name:
    mov ecx, [rax]
    or ecx, 0x20202020
    cmp ecx, 0x64616568 ; head
    jne .skull
    cmp byte [rax+4], 0
    je .head
.skull:
    cmp ecx, 0x6C756B73 ; skul
    jne .neck
    movzx ecx, byte [rax+4]
    or cl, 0x20
    cmp cl, 'l'
    jne .neck
    cmp byte [rax+5], 0
    jne .neck
.head:
    cmp dword [rbx+ANCHOR_RANK], 2
    jae .append
    mov dword [rbx+ANCHOR_RANK], 2
    mov [rbx+HEAD], edi
    jmp .append
.neck:
    cmp dword [rbx+ANCHOR_RANK], 0
    jne .append
    mov ecx, [rax]
    or ecx, 0x20202020
    cmp ecx, 0x6B63656E ; neck
    jne .append
    add rax, 4
.neck_number:
    movzx ecx, byte [rax]
    test ecx, ecx
    jz .neck_found
    sub ecx, '0'
    cmp ecx, 9
    ja .append
    inc rax
    jmp .neck_number
.neck_found:
    mov dword [rbx+ANCHOR_RANK], 1
    mov [rbx+HEAD], edi
.append:
    inc dword [rbx+COUNT]
    add rsi, 32
.next:
    inc edi
    jmp .bone
.bones_done:
    cmp dword [rbx+HEAD], -1
    je .unlock
    cmp dword [rbx+COUNT], 0
    je .unlock
    mov rcx, [rbx+RAG]
    lea rdx, [rbx+ROOT_POSE]
    mov r8d, [rbx+ROOT_BONE]
    call [rel header+392]
    xor ecx, ecx
.offset:
    movss xmm0, [r12+rcx*4+0x2294]
    subss xmm0, [rbx+rcx*4+ROOT_POSE+48]
    movss [rbx+rcx*4+ROOT_OFFSET], xmm0
    inc ecx
    cmp ecx, 3
    jb .offset
    mov rax, [rsp+0x20]
    mov [rbx+LAST_TIME], rax
    mov [rbx+START_TIME], rax
    mov dword [rbx+PHASE], 1 ; await a verified terrain pair before pinning
    mov dword [rbx+REASON], 0
    xor edi, edi
    lea rsi, [rel header+BODY]
.dirty:
    mov rcx, [rbx+WORLD]
    mov edx, [rsi]
    call [rel header+408]   ; invalidate existing contacts, not just new pairs
    add rsi, 32
    inc edi
    cmp edi, [rbx+COUNT]
    jb .dirty
    mov dword [rbx+LOCK], 0
    mov eax, 1
    add rsp, 0x28
    ret
.unlock:
    mov dword [rbx+LOCK], 0
.busy:
    xor eax, eax
    add rsp, 0x28
    ret

; Caller holds LOCK. RAX live target or0; reason in EDX. Drop keeps its CURRENT
; physical pose. Zero velocities and refilter contacts without whole-pose reset.
release_carry:
    sub rsp, 0x38
    lock inc qword [rel header+STATS+184]
    mov [rbx+REASON], edx
    mov ecx, [rbx+PHASE]
    mov [rsp+0x20], ecx
    mov dword [rbx+PHASE], 0
    test rax, rax
    jz .done
    mov r12, rax
    mov rcx, [rax+0x650]
    test rcx, rcx
    jz .mine
    cmp rcx, [rbx+DOG_CHAR]
    jne .done               ; never release another dog's new attachment
.mine:
    cmp dword [rsp+0x20], 2
    jne .bodies
    lea rsi, [rel header+BODY]
    call checked_body
    test rax, rax
    jz .bodies
    mov rcx, [rbx+RAG]
    lea rdx, [rbx+ROOT_POSE]
    mov r8d, [rbx+ROOT_BONE]
    call [rel header+392]
    ; Synchronize the harvest/controller position from the physical root only
    ; when dropping; neither this nor the head setter moves the whole ragdoll.
    xor ecx, ecx
.copy:
    mov eax, [r12+rcx*4+0x2264]
    mov [rbx+rcx*4+256], eax
    inc ecx
    cmp ecx, 16
    jb .copy
    xor ecx, ecx
.position:
    movss xmm0, [rbx+rcx*4+ROOT_POSE+48]
    addss xmm0, [rbx+rcx*4+ROOT_OFFSET]
    movd eax, xmm0
    and eax, 0x7FFFFFFF
    cmp eax, 0x4B189680
    jae .bodies
    movss [rbx+rcx*4+304], xmm0
    inc ecx
    cmp ecx, 3
    jb .position
    lea rcx, [r12+8]
    lea rdx, [rbx+256]
    call [rel header+248]
.bodies:
    cmp dword [rbx+COUNT], 0
    je .detach
    xor edi, edi
    lea rsi, [rel header+BODY]
.body:
    call checked_body
    test rax, rax
    jz .next
    mov rcx, [rbx+WORLD]
    mov edx, [rsi]
    lea r8, [rel zero_vector]
    mov r9, r8
    call [rel header+472]
    mov rcx, [rbx+WORLD]
    mov edx, [rsi]
    call [rel header+408]
.next:
    add rsi, 32
    inc edi
    cmp edi, [rbx+COUNT]
    jb .body
.detach:
    mov rax, [r12+0x650]
    cmp rax, [rbx+DOG_CHAR]
    jne .done
    mov rcx, r12
    call [rel header+416]
.done:
    add rsp, 0x38
    ret

; All added engine calls use these wrappers' existing aligned shadow space.
; Original calls run once before saving the FULL return machine state.
tick_entry:
    NATIVE_START 384
    lock inc qword [rel header+STATS+160]
    lea rbx, [rel header+S]
    cmp dword [rbx+PHASE], 0
    je tick_restore
    xor eax, eax
    mov ecx, 1
    lock cmpxchg [rbx+LOCK], ecx
    jne tick_restore
    call resolve_target
    test rax, rax
    jz tick_invalid
    mov r12, rax
    cmp dword [rbx+PHASE], 3
    jne .live_pickup
    mov edx, [rbx+REASON]
    call release_carry
    jmp tick_unlock
.live_pickup:
    mov dword [rbx+CANCEL_DETAIL], 1 ; current dog component
    mov rax, [rsp+0x28]     ; engine-owned dog component, not a saved pointer
    cmp rax, [rbx+DOG]
    jne tick_cancel
    mov rdx, [rbx+DOG_CHAR]
    mov dword [rbx+CANCEL_DETAIL], 2 ; dog component owner
    cmp [rax+0x18], rdx
    jne tick_cancel
    mov dword [rbx+CANCEL_DETAIL], 3 ; target's native carry link
    cmp [r12+0x650], rdx
    jne tick_cancel
    mov ecx, [rbx+DOG_HANDLE]
    mov dword [rbx+CANCEL_DETAIL], 4 ; dog handle generation
    cmp [rdx+0x2098], ecx
    jne tick_cancel
    mov dword [rbx+CANCEL_DETAIL], 5 ; dog's native carry link
    cmp [rdx+0x650], r12
    jne tick_cancel
    ; Close the input dog back to its current job vector before CHECK_BINDING
    ; may dereference the job. Saved pointers are never treated as engine input.
    mov rcx, [rax+0xC8]
    mov dword [rbx+CANCEL_DETAIL], 6 ; job vector identity
    mov r8, [rax+0xD0]
    test rcx, rcx
    jz tick_cancel
    mov r9, r8
    sub r9, rcx
    jbe tick_cancel
    cmp r9, 256
    ja tick_cancel
    test r9, 7
    jnz tick_cancel
    mov rdx, [rbx+JOB]
.job:
    cmp [rcx], rdx
    je .job_found
    add rcx, 8
    cmp rcx, r8
    jb .job
    jmp tick_cancel
.job_found:
    mov dword [rbx+CANCEL_DETAIL], 7 ; local player/dog/job/lease binding
    mov [rsp+0xE8], rdx
    mov dword [rsp+0xF8], 0
    CHECK_BINDING tick_binding_failed, tick_bound
tick_bound:
    lea rbx, [rel header+S]
    call resolve_target
    test rax, rax
    jz tick_invalid
    mov r12, rax
    xor edi, edi
    lea rsi, [rel header+BODY]
.body_identity:
    call checked_body
    test rax, rax
    jz tick_invalid_bodies
    add rsi, 32
    inc edi
    cmp edi, [rbx+COUNT]
    jb .body_identity
    mov rax, [rsp+0xD0]
    sub rax, [rbx+LAST_TIME]
    mov [rel header+STATS+208], rax
    mov dword [rbx+CANCEL_DETAIL], 8 ; elapsed tick exceeds verified bound
    cmp rax, [rel header+360]
    ja tick_cancel
    ; Mirror native 6CABA0's linked-parent bit47 guard. Pickup can precede
    ; the native carry flag by a frame, so pending waits; active false drops.
    mov rax, [rbx+DOG_CHAR]
    mov rax, [rax+0x2168]
    mov dword [rbx+CANCEL_DETAIL], 9 ; native carry owner absent
    test rax, rax
    jz tick_cancel
    bt qword [rax+0x428], 47
    jc .native_carry
    cmp dword [rbx+PHASE], 2
    je tick_native_drop
    jmp tick_pending
.native_carry:
    cmp dword [rbx+FLOOR], 0
    jne tick_floor_ready
tick_pending:
    mov rax, [rsp+0xD0]
    sub rax, [rbx+START_TIME]
    cmp rax, [rel header+352]
    ja tick_pending_timeout
    mov rax, [rsp+0xD0]
    mov [rbx+LAST_TIME], rax
    jmp tick_unlock
tick_floor_ready:
    mov rcx, [rbx+DOG_CHAR]
    lea rdx, [rel jaw_hash]
    lea r8, [rsp+0x290]
    call [rel header+424]    ; actual Labrador model-space Jaw, hash lookup
    test al, al
    jz tick_bone_missing
    mov rdx, [rbx+DOG_CHAR]
    xor ecx, ecx
.anchor:
    mov dword [rbx+CANCEL_DETAIL], 10 ; nonfinite/out-of-range jaw anchor
    movss xmm0, [rsp+0x2C0]
    mulss xmm0, [rdx+rcx*4+0x2264]
    movss xmm1, [rsp+0x2C4]
    mulss xmm1, [rdx+rcx*4+0x2274]
    addss xmm0, xmm1
    movss xmm1, [rsp+0x2C8]
    mulss xmm1, [rdx+rcx*4+0x2284]
    addss xmm0, xmm1
    addss xmm0, [rdx+rcx*4+0x2294]
    movd eax, xmm0
    and eax, 0x7FFFFFFF
    cmp eax, 0x4B189680
    jae tick_cancel
    movss [rsp+rcx*4+0x310], xmm0
    inc ecx
    cmp ecx, 3
    jb .anchor
    cmp dword [rbx+HAVE_ANCHOR], 0
    je .head
    xorps xmm2, xmm2
    xor ecx, ecx
.jump:
    movss xmm0, [rsp+rcx*4+0x310]
    subss xmm0, [rbx+rcx*4+LAST_ANCHOR]
    mulss xmm0, xmm0
    addss xmm2, xmm0
    inc ecx
    cmp ecx, 3
    jb .jump
    ucomiss xmm2, [rel jump_squared]
    movss [rel header+STATS+200], xmm2
    mov dword [rbx+CANCEL_DETAIL], 11 ; jaw anchor jumped over 3 metres
    ja tick_cancel
.head:
    mov rcx, [rbx+RAG]
    lea rdx, [rsp+0x2D0]
    mov r8d, [rbx+HEAD]
    call [rel header+392]
    xorps xmm2, xmm2
    xor ecx, ecx
    lea r9, [rel header+STATS+224]
.distance:
    movss xmm0, [rsp+rcx*4+0x310]
    movss [r9+rcx*4+48], xmm0 ; jaw world anchor
    movss xmm1, [rsp+rcx*4+0x300]
    movss [r9+rcx*4], xmm1    ; getter world head before setter
    subss xmm0, [rsp+rcx*4+0x300]
    movss [rsp+rcx*4+0x320], xmm0
    mulss xmm0, xmm0
    addss xmm2, xmm0
    inc ecx
    cmp ecx, 3
    jb .distance
    ucomiss xmm2, [rel reach_squared]
    movss [rbx+HEAD_DISTANCE_SQUARED], xmm2
    mov dword [rbx+CANCEL_DETAIL], 12 ; invalid head/anchor distance
    jp tick_cancel
    mov dword [rbx+CANCEL_DETAIL], 13 ; physical head exceeds 10 metre reach
    ja tick_cancel
    sqrtss xmm2, xmm2
    maxss xmm2, [rel epsilon]
    mov rax, [rsp+0xD0]
    sub rax, [rbx+LAST_TIME]
    cvtsi2ss xmm0, rax
    mov rax, [rel header+352]
    cvtsi2ss xmm1, rax
    divss xmm0, xmm1
    mulss xmm0, [rel pin_speed]
    divss xmm0, xmm2
    minss xmm0, [rel one]
    xor ecx, ecx
.move:
    movss xmm1, [rsp+rcx*4+0x320]
    mulss xmm1, xmm0
    movss [rsp+rcx*4+0x320], xmm1 ; one bounded translation shared by all bodies
    addss xmm1, [rsp+rcx*4+0x300]
    movss [rsp+rcx*4+0x300], xmm1
    movss [r9+rcx*4+16], xmm1 ; intended world head setter position
    movss xmm1, [rsp+rcx*4+0x310]
    movss [rbx+rcx*4+LAST_ANCHOR], xmm1
    inc ecx
    cmp ecx, 3
    jb .move
    mov dword [rbx+HAVE_ANCHOR], 1
.translate:
    xor edi, edi
    lea rsi, [rel header+BODY]
.translate_body:
    call checked_body
    test rax, rax
    jz tick_invalid_bodies
    lea rcx, [rel header+BODY]
    mov edx, [rsi]
.unique_body:
    cmp rcx, rsi
    jae .move_body
    cmp [rcx], edx
    je .translate_next      ; skeleton aliases must not translate one body twice
    add rcx, 32
    jmp .unique_body
.move_body:
    mov rcx, [rbx+RAG]
    lea rdx, [rsp+0x2D0]
    mov r8d, [rsi+4]
    call [rel header+392]
    xor ecx, ecx
.translate_xyz:
    movss xmm0, [rsp+rcx*4+0x300]
    addss xmm0, [rsp+rcx*4+0x320]
    movss [rsp+rcx*4+0x300], xmm0
    inc ecx
    cmp ecx, 3
    jb .translate_xyz
    mov rcx, [rbx+RAG]
    mov edx, [rsi+4]
    lea r8, [rsp+0x2D0]
    call [rel header+400]    ; preserve each current rotation and joint-relative pose
    test al, al
    jz tick_bone_missing
    lock inc qword [rel header+STATS+192]
.translate_next:
    add rsi, 32
    inc edi
    cmp edi, [rbx+COUNT]
    jb .translate_body
    mov rcx, [rbx+RAG]
    lea rdx, [rsp+0x2D0]
    mov r8d, [rbx+HEAD]
    call [rel header+392]    ; diagnose immediate setter result in the same space
    lea r9, [rel header+STATS+256]
    xor ecx, ecx
.head_after:
    mov eax, [rsp+rcx*4+0x300]
    mov [r9+rcx*4], eax
    inc ecx
    cmp ecx, 3
    jb .head_after
    lock inc qword [rel header+STATS+176]
    cmp dword [rbx+PHASE], 2
    je .time
    mov dword [rbx+PHASE], 2
    xor edi, edi
    lea rsi, [rel header+BODY]
.refilter:
    mov rcx, [rbx+WORLD]
    mov edx, [rsi]
    call [rel header+408]
    add rsi, 32
    inc edi
    cmp edi, [rbx+COUNT]
    jb .refilter
.time:
    mov dword [rbx+CANCEL_DETAIL], 0
    mov rax, [rsp+0xD0]
    mov [rbx+LAST_TIME], rax
    jmp tick_unlock
tick_pending_timeout:
    mov edx, 6
    cmp dword [rbx+FLOOR], 0
    je tick_release
    mov edx, 8              ; native carry flag was never observed
    jmp tick_release
tick_native_drop:
    mov edx, 1
    jmp tick_release
tick_bone_missing:
    mov edx, 4
    jmp tick_release
tick_binding_failed:
    lea rbx, [rel header+S]
    lea r10, [rel header]
    cmp qword [r10+72], 0
    je tick_cancel
    mov rax, [r10+64]
    test rax, 1
    jnz tick_binding_retry
    cmp rax, [rsp+0xC0]
    je tick_cancel          ; a stable identity failure still detaches
tick_binding_retry:
    lea rcx, [rsp+0xD0]
    mov rax, [r10+32]
    call [rax]
    test eax, eax
    jz tick_cancel
    lea r10, [rel header]
    mov rax, [rsp+0xD0]
    cmp rax, [r10+72]
    jae tick_cancel         ; OFF/expired publications must never defer cleanup
    lock inc qword [rel header+STATS+216]
    jmp tick_unlock         ; publishing race: keep attachment, perform no setters
tick_cancel:
    lea rbx, [rel header+S]
    mov edx, 2
    jmp tick_release
tick_invalid:
    mov edx, 3
tick_release:
    mov [rbx+REASON], edx
    call resolve_target
    mov edx, [rbx+REASON]
    call release_carry
    jmp tick_unlock
tick_invalid_bodies:
    ; A current actor can outlive a destroyed/reused physics body. Do not call
    ; any setter/getter on the changed mapping, even to perform cleanup.
    mov dword [rbx+PHASE], 1 ; suppress root getter/charsetter on changed bodies
    call resolve_target
    mov edx, 3
    call release_carry
tick_unlock:
    mov dword [rbx+LOCK], 0
tick_restore:
    NATIVE_END

align 16
zero_vector: times 4 dd 0
jaw_hash: dd 0x70B05DB4    ; actual Labrador Jaw; never a fixed bone index
jump_squared: dd 9.0
reach_squared: dd 100.0
epsilon: dd 0.0001
pin_speed: dd 20.0
one: dd 1.0
