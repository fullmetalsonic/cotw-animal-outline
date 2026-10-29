"""Fake process boundary and real x64 bytes; never opens the game."""
import hashlib
from contextlib import contextmanager
import struct
import unittest
from unittest.mock import patch

import hellhound_mode as m
from test_pet_outline import FakeAPI as PetAPI, fixture as pet_fixture
from test_ninja_mode import put_qword, put_u32


class FakeAPI(PetAPI):
    def __init__(self):
        super().__init__()
        for rva, data in m.SIGNATURES.items():
            self.put(self.base+rva, data)
        self.put(self.base+m.GATE_RVA, m.ORIGINAL_GATE)
        self.put(self.base+m.PICKUP_CALL_RVA, m.ORIGINAL_PICKUP_CALL)

    def write(self, address, data):
        self.events.append(("write", address, len(data)))
        if not self.running:
            raise OSError("process exited")
        if address in (self.base+m.GATE_RVA, self.base+m.PICKUP_CALL_RVA):
            if self.failure == ("gate_partial" if address == self.base+m.GATE_RVA else "pickup_partial"):
                self.failure = None
                self.put(address, data[:2])
                raise OSError("partial patch")
        if address == self.allocation+m.CODE_SIZE+72 and self.failure == "lease":
            self.failure = None
            self.put(address, data[:8])
            raise OSError("partial publication")
        self.put(address, data)

    def flush(self, address, size):
        self.events.append(("flush", address))
        if address == self.base+m.PICKUP_CALL_RVA and self.failure == "pickup_flush":
            self.failure = None
            raise OSError("cache flush failed")

    def protect(self, address, size, protection):
        if address == self.base+m.PICKUP_CALL_RVA and self.failure == "pickup_protect":
            self.failure = None
            raise OSError("second protection failed")
        return super().protect(address, size, protection)

    @contextmanager
    def frozen_threads(self, site, size):
        with super().frozen_threads(site, size):
            if site == self.base+m.PICKUP_CALL_RVA and self.failure == "pickup_context":
                raise OSError("second thread context failed")
            yield


def fixture(api):
    game, local, extra = pet_fixture(api)
    objects = 0x200000000
    job, vector, host = objects+0x48000, objects+0x4A000, objects+0x50000
    wrapper_slot, wrapper, definition = objects+0x6A000, objects+0x70000, objects+0x74000
    put_qword(api, extra["dog"]+0xC8, vector)
    put_qword(api, extra["dog"]+0xD0, vector+8)
    put_qword(api, vector, job)
    put_qword(api, job, api.base+m.JOB_VTABLE_RVA)
    put_qword(api, job+0x18, extra["dog"])
    put_qword(api, api.base+m.HOST_RVA, host)
    put_qword(api, wrapper_slot, wrapper)
    put_qword(api, wrapper+0x28, definition)
    api.put(definition+0x61, b"\x03")
    api.put(wrapper+0x17C, struct.pack("<f", 0))
    api.put(wrapper+0x19C, struct.pack("<f", 46.91276168823242))
    target, animal_component, ragdoll = objects+0x80000, objects+0x84000, objects+0x86000
    rag_definition, skeleton = objects+0x88000, objects+0x8A000
    source, handle = extra["nodes"]+10*0x180, (6 << 16)|0xBEEF
    identity = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,100.,200.,300.,1.)
    api.put(local["character"]+0x2264, struct.pack("<16f", *identity))
    api.put(target+0x2264, struct.pack("<16f", *identity))
    for address, value in ((target, api.base+m.CHAR_VTABLE_RVA), (target+8, api.base+m.CHAR_INTERFACE_RVA),
                           (api.base+m.CHAR_INTERFACE_RVA+0x98, api.base+m.CHAR_SETTER_RVA),
                           (target+0x1AD0, objects+0x96000), (objects+0x96000+0xC0, objects+0x98000),
                           (target+0x2AC8, animal_component), (animal_component+0x168, wrapper),
                           (wrapper, target), (target+0x1F20, ragdoll), (ragdoll+0x10, rag_definition),
                           (ragdoll+0x78, objects+0x8C000), (ragdoll+0x88, objects+0x8E000),
                           (rag_definition+0x40, skeleton), (rag_definition+0x48, objects+0x90000),
                           (source+0xB8, target)):
        put_qword(api, address, value)
    put_u32(api, target+0x2098, handle)
    put_u32(api, local["mapping"]+24, (10 << 16)|0xBEEF)
    put_u32(api, source+0x170, 1); api.put(source+0x17C, b"\1")
    api.put(source+0x174, struct.pack("<H", 6)); put_u32(api, skeleton+0x30, 30)
    extra.update(job=job, job_vector=vector, host=host, dog_manager=host+0xEBF8,
                 wrapper_slot=wrapper_slot, wrapper=wrapper, definition=definition,
                 target=target, animal_component=animal_component, ragdoll=ragdoll, target_source=source,
                 skeleton=skeleton, identity=identity, result=objects+0x94000)
    return game, local, extra


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.game, self.local, self.extra = fixture(self.api)
        replacement = patch.object(m.probe, "EXPECTED_SHA256", hashlib.sha256(b"fake ninja game").hexdigest())
        replacement.start()
        self.addCleanup(replacement.stop)
        self.mode = m.HellhoundMode(self.game, 1, api=self.api)

    def test_two_site_install_owned_reuse_and_off_only_private_data(self):
        self.assertEqual(self.mode.publish(), 1)
        self.assertEqual(self.mode.last_binding["job"], self.extra["job"])
        gate, weight = self.mode._patches(self.mode.allocation)
        self.assertEqual(self.api.read(self.mode.site, 14), gate)
        self.assertEqual(self.api.read(self.mode.pickup_site, 5), weight)
        self.assertEqual(self.mode.site+11+struct.unpack("<i", gate[7:11])[0], self.api.base+m.REJECT_RVA)
        self.assertEqual(gate[11:], b"\x90"*3)
        self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+72, 8), struct.pack("<Q", 1300))
        self.assertTrue(all(e[1] in (self.mode.site, self.mode.pickup_site)
                            or self.mode.allocation <= e[1] < self.mode.allocation+m.ALLOCATION_SIZE
                            for e in self.api.events if e[0] == "write"))
        mark = len(self.api.events)
        self.mode.disable()
        self.mode.close()
        self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+72, 56), bytes(56))
        self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+256, 80), bytes(80))
        self.assertTrue(all(e[1] >= self.mode.allocation+m.CODE_SIZE for e in self.api.events[mark:] if e[0] == "write"))
        other = m.HellhoundMode(self.game, 2, api=self.api)
        self.assertEqual(other.publish(), 1)
        self.assertEqual(other.allocation, self.mode.allocation)
        self.assertEqual(sum(e[0] == "allocate" for e in self.api.events), 1)
        self.assertEqual(other.read_stats()["gate_total"], 0)
        self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+352, 16), struct.pack("<3fI", 100., 200.35, 303., 1))

    def test_both_sites_restore_and_all_suspend_counts_resume(self):
        for failure in ("gate_partial", "pickup_partial", "pickup_flush", "pickup_protect", "context", "pickup_context"):
            with self.subTest(failure=failure):
                api = FakeAPI()
                game, _, _ = fixture(api)
                mode = m.HellhoundMode(game, 1, api=api)
                api.failure = failure
                with self.assertRaises((RuntimeError, OSError)):
                    mode.publish()
                self.assertEqual(api.read(mode.site, 14), m.ORIGINAL_GATE)
                self.assertEqual(api.read(mode.pickup_site, 5), m.ORIGINAL_PICKUP_CALL)
                self.assertEqual(sum(e[0] == "suspend" for e in api.events), sum(e[0] == "resume" for e in api.events))
                self.assertEqual(api.events[-1], ("resume",))

    def test_job_and_owner_transition_expires_and_recovers(self):
        self.mode.publish()
        for address, data in ((self.extra["dog"]+0xD0, bytes(8)),
                              (self.extra["job"]+0x18, bytes(8)),
                              (self.extra["job"], bytes(8)),
                              (self.extra["meta"], b"\x01"),
                              (self.local["mapping"]+20, struct.pack("<I", 0x00099ABD))):
            with self.subTest(address=address):
                old = self.api.read(address, len(data))
                self.api.put(address, data)
                with self.assertRaises(m.TransientHellhoundState):
                    self.mode.publish()
                self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+72, 8), bytes(8))
                self.api.put(address, old)
                self.assertEqual(self.mode.publish(), 1)

    def test_foreign_mixed_version_hash_and_header_tampering_are_fatal(self):
        with patch.object(self.game.exe, "read_bytes", return_value=b"wrong"):
            with self.assertRaises(RuntimeError):
                self.mode.publish()
        self.assertFalse(self.api.events)
        self.api.put(self.mode.pickup_site, b"\x90"*5)
        with self.assertRaises(RuntimeError):
            self.mode.publish()
        self.assertFalse(self.api.events)
        self.api.put(self.mode.pickup_site, m.ORIGINAL_PICKUP_CALL)
        self.mode.publish()
        self.api.put(self.mode.pickup_site, m.ORIGINAL_PICKUP_CALL)
        with self.assertRaises(RuntimeError):
            m.HellhoundMode(self.game, 1, api=self.api).publish()
        self.api.put(self.mode.pickup_site, self.mode._patches(self.mode.allocation)[1])
        self.api.put(self.mode.allocation+m.CODE_SIZE+240, bytes(8))
        with self.assertRaises(RuntimeError):
            m.HellhoundMode(self.game, 1, api=self.api).publish()
        with self.assertRaises(ValueError):
            m.HellhoundMode(self.game, 1, api=self.api, code=bytes(m.CODE_SIZE))

    def test_lease_write_failure_is_fatal_and_exit_close_idempotent(self):
        self.mode.publish()
        self.api.failure = "lease"
        with self.assertRaises(OSError):
            self.mode.publish()
        self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+72, 8), bytes(8))
        self.api.running = False
        self.mode.close()
        self.mode.close()
        self.assertIsNone(self.mode.allocation)

    def test_destination_uses_native_forward_basis_and_invalid_matrix_expires(self):
        matrix=list(self.extra["identity"])
        # Right=(0,0,-1), up=(0,1,0), forward=(1,0,0).
        matrix[:12]=[0.,0.,-1.,0.,0.,1.,0.,0.,1.,0.,0.,0.]
        self.api.put(self.local["character"]+0x2264,struct.pack("<16f",*matrix))
        self.assertEqual(self.mode._destination(self.local),(103.,200.35,300.))
        self.mode.publish()
        for i,value in ((0,float("nan")),(8,0.),(15,0.),(12,1e8)):
            with self.subTest(i=i):
                bad=matrix.copy();bad[i]=value
                self.api.put(self.local["character"]+0x2264,struct.pack("<16f",*bad))
                with self.assertRaises(m.TransientHellhoundState):self.mode.publish()
                self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+72,8),bytes(8))
        self.api.put(self.local["character"]+0x2264,struct.pack("<16f",*matrix))
        self.mode.publish()


class MachineTests(unittest.TestCase):
    def execute(self, *, kind="gate", animal_class=3, hp=0., active=True, condition=None, original=False):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api = FakeAPI(); game, local, extra = fixture(api)
        mode = m.HellhoundMode(game, 1, api=api)
        binding = mode._binding(); binding["destination"] = mode._destination(binding)
        mode.allocation = api.allocation; mode._publish(binding, 1300 if active else 0)
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(api.base, 0x3000000); uc.mem_map(api.allocation, m.ALLOCATION_SIZE)
        uc.mem_map(0x200000000, 0x100000); uc.mem_map(0x300000000, 0x10000)
        for address, value in api.memory.items(): uc.mem_write(address, bytes([value]))
        header = api.allocation+m.CODE_SIZE
        uc.mem_write(api.allocation, mode.code)
        published = [(o, api.read(header+o, n)) for o,n in ((64,64),(256,80),(352,16))]
        uc.mem_write(header, mode._header()+bytes(m.STATS_SIZE))
        for o,v in published: uc.mem_write(header+o,v)
        uc.mem_write(extra["definition"]+0x61, bytes([animal_class]))
        uc.mem_write(extra["wrapper"]+0x17C, struct.pack("<f", hp))
        qpc = api.base+0x1000
        uc.mem_write(qpc, b"\xc3"); uc.mem_write(api.base+m.QPC_IAT_RVA, struct.pack("<Q", qpc))
        native = api.base+m.PICKUP_FUNCTION_RVA
        uc.mem_write(native, m.SIGNATURES[m.PICKUP_FUNCTION_RVA])
        for rva in (0x69F1A0,0xD83F90,0x698BF0,m.CHAR_SETTER_RVA,m.RAGDOLL_SETTER_RVA):
            uc.mem_write(api.base+rva,b"\xc3")
        gate, pickup = mode._patches(api.allocation)
        uc.mem_write(mode.site,m.ORIGINAL_GATE if original else gate)
        uc.mem_write(mode.pickup_site,m.ORIGINAL_PICKUP_CALL if original else pickup)
        sp=0x300008000
        names=("RAX","RBX","RCX","RDX","RBP","RSI","RDI","R8","R9","R10","R11","R12","R13","R14","R15","RSP")
        regs=dict(zip(names,range(0x100,0x100+len(names))))
        regs.update(RSP=sp, RDI=extra["job"], RDX=extra["wrapper"], RCX=extra["dog_manager"])
        if kind=="pickup":
            regs.update(RCX=extra["result"],RDX=extra["dog_character"],R8=extra["target"],R9=api.base+0x25AA5F0)
        if condition=="foreign_job": regs["RDI"]+=0x100
        if condition=="foreign_dog": regs["RDX"]+=0x100
        for name,value in regs.items(): uc.reg_write(getattr(x,"UC_X86_REG_"+name),value)
        uc.reg_write(x.UC_X86_REG_EFLAGS,0x246)
        for i in range(16): uc.reg_write(getattr(x,"UC_X86_REG_XMM"+str(i)),(0x123456789ABCDEF012345678<<32)|i)
        mutations={
            "expired":(header+72,struct.pack("<Q",1000)),"odd":(header+64,struct.pack("<Q",3)),
            "bad_metadata":(header+256,struct.pack("<Q",1)),"job_link":(extra["job"]+0x18,bytes(8)),
            "job_vtable":(extra["job"],bytes(8)),"owner":(extra["meta"],b"\1"),
            "dog_generation":(local["mapping"]+20,struct.pack("<I",0x00099ABD)),
            "player_rebind":(extra["local_slot"]+0x170,bytes(8)),"world":(extra["world"]+0x48,bytes(4)),
            "bad_dest":(header+352,struct.pack("<f",float("nan"))),"dest_disabled":(header+364,bytes(4)),
            "bad_pose":(extra["target"]+0x2264,struct.pack("<f",float("inf"))),
            "pose_w":(extra["target"]+0x22A0,bytes(4)),"wrapper_ref":(extra["wrapper"],bytes(8)),
            "target_generation":(local["mapping"]+24,struct.pack("<I",0x000ABEEE)),
            "controller_missing":(extra["target"]+0x1AD0,bytes(8)),
            "controller_body_missing":(0x200096000+0xC0,bytes(8)),
            "ragdoll_missing":(extra["target"]+0x1F20,bytes(8)),
            "ragdoll_count":(extra["skeleton"]+0x30,struct.pack("<I",10000)),
            "setter_changed":(api.base+m.CHAR_INTERFACE_RVA+0x98,bytes(8)),
        }
        if condition in mutations: uc.mem_write(*mutations[condition])
        calls=[]; writes=[]; results={}; native_args=[]; native_state={}
        stops=(mode.site+14,api.base+m.REJECT_RVA) if kind=="gate" else (mode.pickup_site+5,)
        def clobber(machine, all_regs=False):
            for n in (("RAX","RCX","RDX","R8","R9","R10","R11") if not all_regs else names[:-1]):
                machine.reg_write(getattr(x,"UC_X86_REG_"+n),0xBAD)
            for i in range(16 if all_regs else 6): machine.reg_write(getattr(x,"UC_X86_REG_XMM"+str(i)),0xBAD)
            machine.reg_write(x.UC_X86_REG_EFLAGS,0x202)
        def trace(machine,address,size,_):
            if address in stops:
                results["stop"]=address; machine.emu_stop(); return
            if address in (qpc,native,api.base+m.CHAR_SETTER_RVA,api.base+m.RAGDOLL_SETTER_RVA):
                self.assertEqual(machine.reg_read(x.UC_X86_REG_RSP)%16,8)
            # The native return RDX points into its now-dead stack frame. Capture
            # this real invocation, including that exact pointer and ADD-RSP flags.
            if address==native+len(m.SIGNATURES[m.PICKUP_FUNCTION_RVA])-1:
                native_state["registers"]={n:machine.reg_read(getattr(x,"UC_X86_REG_"+n)) for n in names}
                native_state["registers"]["RSP"]=sp
                native_state["xmm"]=[machine.reg_read(getattr(x,"UC_X86_REG_XMM"+str(i))) for i in range(16)]
                native_state["flags"]=machine.reg_read(x.UC_X86_REG_EFLAGS)
            if address==native:
                native_args.append(tuple(machine.reg_read(getattr(x,"UC_X86_REG_"+n)) for n in ("RCX","RDX","R8","R9")))
            elif address==qpc:
                machine.mem_write(machine.reg_read(x.UC_X86_REG_RCX),struct.pack("<Q",1000));clobber(machine)
                machine.reg_write(x.UC_X86_REG_RAX,condition!="qpc_fail")
                if condition=="sequence_race": machine.mem_write(header+64,struct.pack("<Q",8))
                if condition=="post_qpc_job": machine.mem_write(extra["job"]+0x18,bytes(8))
                if condition=="post_qpc_target": machine.mem_write(extra["target"]+0x2098,struct.pack("<I",0x6BEF0))
            elif address==api.base+0x69F1A0:
                self.assertEqual(machine.reg_read(x.UC_X86_REG_RCX),regs["R8"])
                self.assertEqual(machine.reg_read(x.UC_X86_REG_RDX),regs["RDX"])
                if condition=="native_failed": machine.mem_write(extra["result"],b"\0")
            elif address==api.base+0xD83F90:
                machine.reg_write(x.UC_X86_REG_RAX,0xABD335B1)
            elif address==api.base+m.CHAR_SETTER_RVA:
                c=machine.reg_read(x.UC_X86_REG_RCX); a=machine.reg_read(x.UC_X86_REG_RDX)
                matrix=bytes(machine.mem_read(a,64));calls.append(("character",c,a,matrix))
                self.assertEqual(c,extra["target"]+8)
                machine.mem_write(extra["target"]+0x2264,matrix);clobber(machine,True)
            elif address==api.base+m.RAGDOLL_SETTER_RVA:
                c=machine.reg_read(x.UC_X86_REG_RCX);a=machine.reg_read(x.UC_X86_REG_RDX)
                calls.append(("ragdoll",c,a,bytes(machine.mem_read(a,64))))
                self.assertEqual(c,extra["ragdoll"])
                self.assertEqual(machine.reg_read(x.UC_X86_REG_R8),0)
                self.assertEqual(machine.reg_read(x.UC_X86_REG_R9),0);clobber(machine,True)
        def watch(machine,access,address,size,value,_): writes.append((address,size))
        uc.hook_add(UC_HOOK_CODE,trace); uc.hook_add(UC_HOOK_MEM_WRITE,watch)
        uc.emu_start(mode.site if kind=="gate" else mode.pickup_site,0,count=20000)
        self.assertIn("stop",results)
        self.assertTrue(all(0x300000000<=a<0x300010000 or header+m.HEADER_SIZE<=a<header+m.HEADER_SIZE+m.STATS_SIZE
                            or (kind=="pickup" and extra["result"]<=a<extra["result"]+16) for a,n in writes),writes)
        if kind=="pickup":
            self.assertEqual({n:uc.reg_read(getattr(x,"UC_X86_REG_"+n)) for n in names}, native_state["registers"])
            self.assertEqual([uc.reg_read(getattr(x,"UC_X86_REG_XMM"+str(i))) for i in range(16)],native_state["xmm"])
            self.assertEqual(uc.reg_read(x.UC_X86_REG_EFLAGS),native_state["flags"])
        return dict(accepted=results["stop"]==mode.site+14,
                    registers={n:uc.reg_read(getattr(x,"UC_X86_REG_"+n)) for n in names},
                    xmm=[uc.reg_read(getattr(x,"UC_X86_REG_XMM"+str(i))) for i in range(16)],
                    flags=uc.reg_read(x.UC_X86_REG_EFLAGS),calls=calls,native_args=native_args,
                    stats=struct.unpack("<6Q",uc.mem_read(header+384,48)),
                    mass=struct.unpack("<2f",uc.mem_read(header+456,8)))

    def test_generated_hash_and_entry_boundaries(self):
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64
        code=m.HellhoundMode(None,None,api=FakeAPI()).code
        self.assertEqual(len(code),8192);self.assertEqual(hashlib.sha256(code).hexdigest(),m.STUB_SHA256)
        self.assertEqual(next(Cs(CS_ARCH_X86,CS_MODE_64).disasm(code,0)).mnemonic,"mov")
        self.assertEqual(next(Cs(CS_ARCH_X86,CS_MODE_64).disasm(code[m.PICKUP_OFFSET:],m.PICKUP_OFFSET)).mnemonic,"pushfq")

    def test_gate_classes_and_native_flags(self):
        for c in (0,1,2,3,4,5,6,7,8,9,10,255):
            with self.subTest(c=c):
                actual=self.execute(animal_class=c);self.assertEqual(actual["accepted"],1<=c<=9)
                native=self.execute(animal_class=c,original=True)
                self.assertEqual(actual["registers"],native["registers"]);self.assertEqual(actual["xmm"],native["xmm"])
                if c not in range(2,10):self.assertEqual(actual["flags"],native["flags"])
        for hp in (1.,float("nan"),float("inf"),-float("inf")):
            self.assertFalse(self.execute(hp=hp)["accepted"])
        for hp in (-0.,-1.):self.assertTrue(self.execute(hp=hp)["accepted"])

    def test_gate_fallbacks_exact_native(self):
        for c in ("expired","odd","bad_metadata","foreign_job","job_link","job_vtable","owner","dog_generation",
                  "player_rebind","world","qpc_fail","sequence_race","post_qpc_job"):
            with self.subTest(c=c):
                a=self.execute(condition=c);n=self.execute(original=True,condition=c)
                self.assertFalse(a["accepted"]);self.assertEqual(a["registers"],n["registers"])
                self.assertEqual(a["xmm"],n["xmm"]);self.assertEqual(a["flags"],n["flags"])
        self.assertFalse(self.execute(active=False)["accepted"])

    def test_pickup_all_extended_classes_exact_native_abi_and_two_setters(self):
        for c in range(2,10):
            with self.subTest(c=c):
                a=self.execute(kind="pickup",animal_class=c);n=self.execute(kind="pickup",animal_class=c,original=True)
                self.assertEqual(a["xmm"],n["xmm"]);self.assertEqual(a["native_args"],n["native_args"])
                self.assertEqual(len(a["native_args"]),1);self.assertEqual([v[0] for v in a["calls"]],["character","ragdoll"])
                self.assertEqual(a["calls"][0][2:],a["calls"][1][2:])
                matrix=struct.unpack("<16f",a["calls"][0][3])
                self.assertEqual(matrix[:12],(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.))
                self.assertAlmostEqual(matrix[12],100.);self.assertAlmostEqual(matrix[13],200.35,places=4)
                self.assertAlmostEqual(matrix[14],303.);self.assertEqual(a["mass"][0],a["mass"][1])
                self.assertEqual(a["stats"][3:],(1,1,0))

    def test_pickup_fallbacks_original_once_and_full_return_state(self):
        cases=[dict(animal_class=c) for c in (0,1,10,255)]
        cases += [dict(hp=h) for h in (1.,float("nan"),float("inf"),-float("inf"))]
        cases += [dict(condition=c) for c in ("expired","odd","bad_metadata","foreign_dog","job_link","job_vtable",
                  "owner","dog_generation","player_rebind","world","qpc_fail","sequence_race","post_qpc_job",
                  "post_qpc_target","bad_dest","dest_disabled","bad_pose","pose_w","wrapper_ref","target_generation",
                  "controller_missing","controller_body_missing","ragdoll_missing","ragdoll_count","setter_changed","native_failed")]
        cases.append(dict(active=False))
        for case in cases:
            with self.subTest(case=case):
                a=self.execute(kind="pickup",**case);n=self.execute(kind="pickup",original=True,**case)
                self.assertEqual(a["calls"],[]);self.assertEqual(len(a["native_args"]),1)
                self.assertEqual(a["native_args"],n["native_args"]);self.assertEqual(a["xmm"],n["xmm"])


if __name__ == "__main__":
    unittest.main()
