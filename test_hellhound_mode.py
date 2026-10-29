"""Real x64 carry bytes on Unicorn. Native physics is an ABI double, not Havok."""
from contextlib import contextmanager
import hashlib
import struct
import unittest
from unittest.mock import patch
import hellhound_mode as m
from test_pet_outline import FakeAPI as PetAPI, fixture as pet_fixture
from test_ninja_mode import put_qword, put_u32

class FakeAPI(PetAPI):
    def __init__(self):
        super().__init__()
        for r,d in m.SIGNATURES.items():self.put(self.base+r,d)
        for r,d in ((m.GATE_RVA,m.ORIGINAL_GATE),(m.PICKUP_CALL_RVA,m.ORIGINAL_PICKUP_CALL),(m.TICK_CALL_RVA,m.ORIGINAL_TICK_CALL),(m.SPEED_CALL_RVA,m.ORIGINAL_SPEED_CALL),(m.PAIR_SITE_RVA,struct.pack('<Q',self.base+m.PAIR_FUNCTION_RVA))):self.put(self.base+r,d)
    def write(self,a,d):
        self.events.append(('write',a,len(d)))
        if not self.running:raise OSError('exited')
        if self.failure==('partial',a):self.failure=None;self.put(a,d[:2]);raise OSError('partial patch')
        if self.failure=='lease' and a==self.allocation+m.CODE_SIZE+72:self.failure=None;self.put(a,d[:8]);raise OSError('partial lease')
        self.put(a,d)
    @contextmanager
    def frozen_threads(self,site,size):
        with super().frozen_threads(site,size):
            if self.failure==('context',site):raise OSError('context')
            yield

def fixture(api):
    game,local,e=pet_fixture(api);o=0x200000000
    e.update(job=o+0x48000,vector=o+0x4A000,host=o+0x50000,wrapper=o+0x70000,definition=o+0x74000,target=o+0x80000,animal=o+0x84000,rag=o+0x86000,ragdef=o+0x88000,skel=o+0x8A000,bone_map=o+0x8C000,ids=o+0x8C100,bones=o+0x8D000,root_name=o+0x8E000,head_name=o+0x8E020,result=o+0x94000,physics=o+0xA0000,bodies=o+0xA4000,physics_manager=o+0xB0000,terrain=o+0xB1000,pairs=o+0xB2000,shapes=o+0xB4000)
    for a,v in ((e['dog_character']+0x2168,o+0xC0000),(o+0xC0428,1<<47),(e['dog']+0xC8,e['vector']),(e['dog']+0xD0,e['vector']+8),(e['vector'],e['job']),(e['job'],api.base+m.JOB_VTABLE_RVA),(e['job']+0x18,e['dog']),(api.base+m.HOST_RVA,e['host']),(e['wrapper'],e['target']),(e['wrapper']+0x28,e['definition']),(e['target'],api.base+m.CHAR_VTABLE_RVA),(e['target']+8,api.base+m.CHAR_INTERFACE_RVA),(api.base+m.CHAR_INTERFACE_RVA+0x98,api.base+m.CHAR_SETTER_RVA),(e['target']+0x2AC8,e['animal']),(e['animal']+0x168,e['wrapper']),(e['target']+0x1F20,e['rag']),(e['rag']+8,e['physics']),(e['rag']+0x10,e['ragdef']),(e['rag']+0x78,o+0x96000),(e['rag']+0x88,o+0x98000),(e['target']+0x1AD0,o+0x99000),(o+0x99000+0xC0,o+0x99100),(e['ragdef']+0x40,e['skel']),(e['ragdef']+0x48,e['bone_map']),(e['ragdef']+0x20,e['ids']),(e['skel']+0x28,e['bones']),(e['bones'],e['root_name']),(e['bones']+16,e['head_name']),(e['physics']+0x20,e['bodies']),(api.base+0x27A8320,e['physics_manager']),(e['physics_manager']+0x30,e['physics']),(e['physics_manager']+0x1A078,e['terrain']),(e['terrain'],api.base+0x1984248)):put_qword(api,a,v)
    api.put(e['definition']+0x61,b'\3');api.put(e['wrapper']+0x17C,bytes(4));api.put(e['wrapper']+0x19C,struct.pack('<f',46.91276))
    e['handle']=(6<<16)|0xBEEF;put_u32(api,e['target']+0x2098,e['handle']);put_u32(api,local['mapping']+24,(10<<16)|0xBEEF)
    e['target_source']=e['nodes']+10*0x180;src=e['target_source'];put_qword(api,src+0xB8,e['target']);put_u32(api,src+0x170,1);api.put(src+0x17C,b'\1');api.put(src+0x174,struct.pack('<H',6))
    put_u32(api,e['skel']+0x30,2);api.put(e['bone_map'],struct.pack('<2i',0,1));api.put(e['ids'],struct.pack('<2I',10,11));api.put(e['root_name'],b'Pelvis\0');api.put(e['head_name'],b'Head\0');put_u32(api,e['physics']+0x28,100);put_u32(api,e['terrain']+0x38,0x10003)
    pose=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,100.,200.,300.,1.];e['identity']=pose
    api.put(e['target']+0x2264,struct.pack('<16f',*pose));dog=pose.copy();dog[12]=102.;api.put(e['dog_character']+0x2264,struct.pack('<16f',*dog))
    for i,flags,filt in ((1,1,0x10003),(2,1,5),(3,2,2),(10,2,2),(11,2,2)):
        a=e['bodies']+i*0x90;p=pose.copy();p[13]+=i==11;api.put(a,struct.pack('<16f',*p))
        for off,v in ((0x40,flags),(0x44,filt),(0x60,i),(0x68,i)):put_u32(api,a+off,v)
        put_qword(api,a+0x48,e['shapes']+i*16);put_qword(api,a+0x88,e['target'] if i>=10 else 0);put_qword(api,e['shapes']+i*16,api.base+(0x223C008 if i==1 else 0x1FE1CF8))
    return game,local,e

class Machine:
    def __init__(self,t,c=3):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn import x86_const
        self.t=t;self.x=x86_const;self.api=FakeAPI();self.game,self.local,self.e=fixture(self.api);self.mode=m.HellhoundMode(self.game,1,api=self.api);self.mode.publish();self.h=self.api.allocation+m.CODE_SIZE
        self.u=Uc(UC_ARCH_X86,UC_MODE_64)
        for a,n in ((self.api.base,0x3000000),(self.api.allocation,m.ALLOCATION_SIZE),(0x200000000,0x200000),(0x300000000,0x10000)):self.u.mem_map(a,n)
        start=last=0;data=bytearray()
        for a in sorted(self.api.memory):
            if a!=last+1:
                if data:self.u.mem_write(start,bytes(data))
                start=a;data=bytearray()
            data.append(self.api.memory[a]);last=a
        if data:self.u.mem_write(start,bytes(data))
        self.put(self.e['definition']+0x61,bytes([c]));self.now=1000;self.qpc=self.api.base+0x1000;self.put(self.api.base+m.QPC_IAT_RVA,struct.pack('<Q',self.qpc));self.stop=self.api.base+0x1800
        self.calls=[];self.post={};self.missing_jaw=False;self.mutation=None;self.keep=None;self.writes=[];self.origin=(0.,0.,0.)
        self.originals={m.PICKUP_FUNCTION_RVA:'pickup',m.TICK_FUNCTION_RVA:'tick',m.SPEED_FUNCTION_RVA:'speed',m.PAIR_FUNCTION_RVA:'pair'}
        self.helpers=(0x3223A0,0x3320E0,0xFCF7A0,0x69DB70,0x67A0B0,0xFCDA50,m.CHAR_SETTER_RVA)
        for r in (*self.originals,*self.helpers):self.put(self.api.base+r,b'\xc3')
        self.put(self.qpc,b'\xc3');self.u.hook_add(UC_HOOK_CODE,self.trace)
        self.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,a,n,value,data:self.writes.append((a,n)))
    def reg(self,n):return self.u.reg_read(getattr(self.x,'UC_X86_REG_'+n))
    def setreg(self,n,v):self.u.reg_write(getattr(self.x,'UC_X86_REG_'+n),v)
    def put(self,a,d):self.u.mem_write(a,d)
    def raw(self,a,n):return bytes(self.u.mem_read(a,n))
    def put32(self,a,v):self.put(a,struct.pack('<I',v))
    def u32(self,a):return struct.unpack('<I',self.raw(a,4))[0]
    def phase(self,off=0):return self.u32(self.h+m.STATE_OFFSET+off)
    def skeleton(self,names):
        self.put32(self.e['skel']+0x30,len(names))
        self.put(self.e['bone_map'],struct.pack('<'+'i'*len(names),*range(len(names))))
        self.put(self.e['ids'],struct.pack('<'+'I'*len(names),*(10+i for i in range(len(names)))))
        for i,name in enumerate(names):
            address=self.e['root_name']+i*32
            self.put(self.e['bones']+i*16,struct.pack('<Q',address));self.put(address,name.encode('ascii')+b'\0')
            body=self.e['bodies']+(10+i)*0x90
            self.put(body,struct.pack('<16f',*self.e['identity']))
            for offset,value in ((0x40,2),(0x44,2),(0x60,10+i),(0x68,10+i)):self.put32(body+offset,value)
            self.put(body+0x48,struct.pack('<Q',self.e['shapes']+(10+i)*16))
            self.put(body+0x88,struct.pack('<Q',self.e['target']))
    def snap(self):return ({n:self.reg(n) for n in ('RAX','RBX','RCX','RDX','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15')},[self.reg('XMM'+str(i)) for i in range(16)],self.reg('EFLAGS'))
    def clobber(self,result=1):
        for i,n in enumerate(('RAX','RCX','RDX','R8','R9','R10','R11')):self.setreg(n,0xBAD000+i)
        for i in range(6):self.setreg('XMM'+str(i),0xABC000+i)
        self.setreg('RAX',result);self.setreg('EFLAGS',0x202)
    def trace(self,u,a,size,_):
        if a==self.stop:u.emu_stop();return
        args=tuple(self.reg(n) for n in ('RCX','RDX','R8','R9'))
        if a==self.qpc:
            self.t.assertEqual(self.reg('RSP')%16,8);self.put(args[0],struct.pack('<Q',self.now));self.clobber()
            if self.mutation:self.mutation(self);self.mutation=None
            return
        r=a-self.api.base
        if r in self.originals:
            n=self.originals[r];self.calls.append((n,args));self.t.assertEqual(self.reg('RSP')%16,8)
            if n=='pickup':
                self.put(args[0],b'\1')
                for c,p in ((args[1],args[2]),(args[2],args[1])):self.put(c+0x650,struct.pack('<2Q',p,self.e['result']))
            if n=='pair':
                ps=[self.raw(args[2]+i*8,8) for i in range(args[3])]
                if self.keep is not None:ps=[ps[i] for i in self.keep]
                for i,p in enumerate(ps):self.put(args[2]+i*8,p)
                self.clobber(len(ps))
            else:self.clobber()
            if n=='speed':self.setreg('XMM0',int.from_bytes(struct.pack('<f',.65),'little'))
            self.post[n]=self.snap();return
        if r not in self.helpers:return
        self.t.assertEqual(self.reg('RSP')%16,8);self.calls.append((hex(r),args));result=1
        if r in (0x3223A0,0x3320E0):
            i=args[2] if r==0x3223A0 else args[1];self.t.assertLess(i,self.u32(self.e['skel']+0x30))
            mapped=self.u32(self.e['bone_map']+i*4);self.t.assertLess(mapped,256)
            body_id=self.u32(self.e['ids']+mapped*4);b=self.e['bodies']+body_id*0x90
            pose=list(struct.unpack('<16f',self.raw(b if r==0x3223A0 else args[2],64)))
            for axis in range(3):pose[12+axis]+=self.origin[axis] if r==0x3223A0 else -self.origin[axis]
            self.put(args[1] if r==0x3223A0 else b,struct.pack('<16f',*pose))
        elif r==0x67A0B0:
            self.t.assertEqual(self.u32(args[1]),0x70B05DB4);p=self.e['identity'].copy();p[12:15]=[0.,1.,.5];self.put(args[2],struct.pack('<16f',*p));result=not self.missing_jaw
        elif r==m.CHAR_SETTER_RVA:self.t.assertEqual(args[0],self.e['target']+8);self.put(self.e['target']+0x2264,self.raw(args[1],64))
        elif r==0x69DB70:
            for b in (self.e['target'],self.e['dog_character']):self.put(b+0x650,bytes(16))
        elif r==0xFCDA50:self.t.assertEqual(self.raw(args[2],16),bytes(16));self.t.assertEqual(self.raw(args[3],16),bytes(16))
        self.clobber(int(result))
    def run(self,kind,pairs=None):
        offsets={'gate':0,'pickup':m.PICKUP_OFFSET,'tick':m.TICK_OFFSET,'pair':m.PAIR_OFFSET,'speed':m.SPEED_OFFSET}
        args={'gate':(self.e['host']+0xEBF8,self.e['wrapper'],0,0),'pickup':(self.e['result'],self.e['dog_character'],self.e['target'],self.api.base+0x25AA5F0),'tick':(self.e['dog'],0,0,0),'speed':(self.e['job'],0,0,0)}
        if kind=='pair':
            ps=pairs or [(10,1),(10,2),(11,3),(10,11),(2,3)];self.put(self.e['pairs'],b''.join(struct.pack('<2I',*p) for p in ps));args['pair']=(self.api.base+0x2800,self.e['physics'],self.e['pairs'],len(ps))
        for i,n in enumerate(('RAX','RBX','RCX','RDX','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15')):self.setreg(n,0xF000+i)
        for n,v in zip(('RCX','RDX','R8','R9'),args[kind]):self.setreg(n,v)
        if kind=='gate':self.setreg('RDI',self.e['job'])
        for i in range(16):self.setreg('XMM'+str(i),0x123456780000+i)
        self.setreg('EFLAGS',0x246);self.setreg('RSP',0x300008008);self.put(0x300008008,struct.pack('<Q',self.stop))
        self.u.emu_start(self.api.allocation+offsets[kind],self.stop,count=500000);self.t.assertEqual(self.reg('RIP'),self.stop)
        if kind not in ('speed','pair','gate'):self.t.assertEqual(self.snap(),self.post[kind])
        self.t.assertTrue(all(self.h<=a<a+n<=self.api.allocation+m.ALLOCATION_SIZE or 0x300000000<=a<a+n<=0x300010000 or self.e['pairs']<=a<a+n<=self.e['pairs']+4096*8 for a,n in self.writes))
        if kind=='pair':return [struct.unpack('<2I',self.raw(self.e['pairs']+i*8,8)) for i in range(self.reg('RAX'))]
    def carry(self):
        self.run('pickup');self.t.assertEqual(self.phase(),1);self.run('pair');self.t.assertEqual(self.phase(124),1);self.now+=16;self.run('tick');self.t.assertEqual(self.phase(),2)

class Tests(unittest.TestCase):
    def setUp(self):
        p=patch.object(m.probe,'EXPECTED_SHA256',hashlib.sha256(b'fake ninja game').hexdigest());p.start();self.addCleanup(p.stop)
    def test_five_site_transaction_off_reuse_and_each_partial_rollback(self):
        api=FakeAPI();g,_,_=fixture(api);mode=m.HellhoundMode(g,1,api=api);mode.publish();a=mode.allocation
        self.assertEqual(tuple(api.read(p,len(v)) for p,v in mode._sites()),mode._patches(a));mode.disable();mode.close();self.assertEqual(api.read(a+m.CODE_SIZE+72,8),bytes(8))
        other=m.HellhoundMode(g,2,api=api);other.publish();self.assertEqual(other.allocation,a);self.assertEqual(other.read_stats()['phase'],0)
        for kind in ('partial','context'):
            for i in range(5):
                with self.subTest(kind=kind,i=i):
                    api=FakeAPI();g,_,_=fixture(api);mode=m.HellhoundMode(g,1,api=api);api.failure=(kind,mode._sites()[i][0])
                    with self.assertRaises((RuntimeError,OSError)):mode.publish()
                    self.assertEqual(tuple(api.read(p,len(v)) for p,v in mode._sites()),tuple(v for p,v in mode._sites()))
                    self.assertEqual(sum(x[0]=='suspend' for x in api.events),sum(x[0]=='resume' for x in api.events))
    def test_hash_foreign_site_and_lease_failure(self):
        api=FakeAPI();g,_,e=fixture(api);mode=m.HellhoundMode(g,1,api=api)
        with patch.object(g.exe,'read_bytes',return_value=b'wrong'):
            with self.assertRaises(RuntimeError):mode.publish()
        self.assertFalse(api.events);mode.publish();api.failure='lease'
        with self.assertRaises(OSError):mode.publish()
        self.assertEqual(api.read(mode.allocation+m.CODE_SIZE+72,8),bytes(8));api.put(mode.game.base+m.PAIR_SITE_RVA,bytes(8))
        with self.assertRaises(RuntimeError):mode.publish()
        api.running=False;mode.close();mode.close();self.assertIsNone(mode.allocation)
    def test_all_classes_original_once_no_instant_teleport_then_common_body_delta(self):
        for c in range(2,10):
            with self.subTest(c=c):
                a=Machine(self,c);before=a.raw(a.e['target']+0x2264,64);a.carry();self.assertEqual(a.raw(a.e['target']+0x2264,64),before)
                self.assertEqual(sum(n=='pickup' for n,_ in a.calls),1);self.assertEqual([v[1] for n,v in a.calls if n=='0x3320e0'],[0,1]);self.assertEqual(a.raw(a.e['wrapper']+0x19C,4),struct.pack('<f',46.91276))
                base=a.h+m.HEADER_SIZE
                self.assertEqual(a.raw(base+240,12),a.raw(base+256,12))
                self.assertEqual(struct.unpack('<3f',a.raw(base+224,12)),(100.,201.,300.))
                self.assertEqual(struct.unpack('<3f',a.raw(base+272,12)),(102.,201.,300.5))
                root=struct.unpack('<16f',a.raw(a.e['bodies']+10*0x90,64));head=struct.unpack('<16f',a.raw(a.e['bodies']+11*0x90,64))
                self.assertEqual(root[:12],tuple(a.e['identity'][:12]))
                self.assertAlmostEqual(head[12]-root[12],0.,places=4);self.assertAlmostEqual(head[13]-root[13],1.,places=4)
                self.assertAlmostEqual(head[14]-root[14],0.,places=4)
    def test_native_class1_out_of_range_and_living_fallback(self):
        for c in (0,1,10,255):
            a=Machine(self,c);a.run('pickup');self.assertEqual(a.phase(),0);self.assertEqual([n for n,_ in a.calls],['pickup'])
        for hp in (1.,float('nan'),float('inf'),-float('inf')):
            a=Machine(self);a.put(a.e['wrapper']+0x17C,struct.pack('<f',hp));a.run('pickup');self.assertEqual(a.phase(),0)
    def test_live_taruca_ragdoll_names_choose_head_after_necks_and_ignore_jaw(self):
        # Exact order from the read-only 2026-10-30 Taruca physical skeleton capture.
        names=('Hips LeftPelvis RightPelvis Spine Tail01 LeftUpLeg RightUpLeg Spine2 LeftLeg RightLeg '
               'LeftShoulder01 Neck01 RightShoulder01 LeftFoot RightFoot LeftShoulder02 Neck02 '
               'RightShoulder02 LeftArm Neck03 RightArm LeftForeArm Head RightForeArm LeftHand fJaw RightHand').split()
        a=Machine(self);a.skeleton(['ragdoll_'+name for name in names]);a.carry()
        self.assertEqual(a.phase(100),22);self.assertEqual(a.phase(180),2)
        self.assertEqual([v[1] for n,v in a.calls if n=='0x3320e0'],list(range(27)))
        root=a.raw(a.e['bodies']+10*0x90,64)
        self.assertTrue(all(a.raw(a.e['bodies']+(10+i)*0x90,64)==root for i in range(27)))
    def test_common_translation_keeps_rotations_and_relative_pose_with_world_origin_shift_and_aliases(self):
        a=Machine(self);a.origin=(7800.,0.,-8113.)
        original=[]
        for i in range(2):
            body=a.e['bodies']+(10+i)*0x90;pose=list(struct.unpack('<16f',a.raw(body,64)))
            if i==1:pose[:12]=[0.,0.,1.,0.,0.,1.,0.,0.,-1.,0.,0.,0.]
            for axis in range(3):pose[12+axis]-=a.origin[axis]
            a.put(body,struct.pack('<16f',*pose));original.append(pose)
        a.carry();deltas=[]
        for i in range(2):
            pose=struct.unpack('<16f',a.raw(a.e['bodies']+(10+i)*0x90,64));self.assertEqual(pose[:12],tuple(original[i][:12]))
            deltas.append([pose[12+j]-original[i][12+j] for j in range(3)])
        for axis in range(3):self.assertAlmostEqual(deltas[0][axis],deltas[1][axis],places=3)
        self.assertLessEqual(sum(v*v for v in deltas[0])**.5,.321)
        a=Machine(self);a.skeleton(['ragdoll_Hips','rig:Neck02','rig:Head'])
        a.put32(a.e['bone_map']+8,1);a.carry()
        self.assertEqual(a.phase(100),2);self.assertEqual([v[1] for n,v in a.calls if n=='0x3320e0'],[0,1])
    def test_exact_head_and_neck_names_and_unmapped_head_fail_closed(self):
        for name in ('Head','internal_skull','ragdoll_Head','ragdoll_internal_skull',
                     'Neck','Neck01','Neck02','Neck03','ragdoll_Neck','ragdoll_Neck01','ragdoll_Neck02','ragdoll_Neck03',
                     'Neck04','rig:HEAD','Armature|skull','animal.rig/Neck12','other_prefix_Head','ragdol_Head'):
            with self.subTest(name=name):
                a=Machine(self);a.skeleton(['ragdoll_Hips',name]);a.carry();self.assertEqual(a.phase(100),1)
        for name in ('ragdoll_Head_extra','ragdoll_fJaw','Neck01tail','HeadNeck','ragdoll_LeftArm','forehead','necklace',
                     'rig/Neck01helper','a'*128+'_Head'):
            with self.subTest(name=name):
                a=Machine(self);a.skeleton(['ragdoll_Hips',name]);a.run('pickup');self.assertEqual(a.phase(),3)
                a.run('tick');self.assertEqual(a.phase(),0);self.assertEqual(a.phase(144),4)
                self.assertFalse(any(n=='0x3320e0' for n,_ in a.calls))
        a=Machine(self);a.skeleton(['ragdoll_Hips','ragdoll_Head']);a.put32(a.e['bone_map']+4,0xFFFFFFFF)
        a.run('pickup');self.assertEqual(a.phase(),3);a.run('tick');self.assertEqual(a.phase(),0)
        a=Machine(self);a.skeleton(['ragdoll_Hips','ragdoll_Neck02','ragdoll_Head'])
        a.put32(a.e['bone_map']+8,0xFFFFFFFF);a.carry();self.assertEqual(a.phase(100),1)
        a=Machine(self);a.skeleton(['ragdoll_Hips','Neck02','ragdoll_Neck01']);a.carry();self.assertEqual(a.phase(100),1)
    def test_collision_transport_scope_ground_native_self_and_unrelated_pairs(self):
        a=Machine(self);a.run('pickup');ps=[(10,1),(10,2),(11,3),(10,11),(2,3)];self.assertEqual(a.run('pair',ps),ps);a.now+=16;a.run('tick')
        self.assertEqual(a.run('pair',ps),[(10,1),(10,11),(2,3)]);a.keep=[1,4];self.assertEqual(a.run('pair',ps),[(2,3)])
        a.keep=None;self.assertEqual(a.run('pair',[(1,10),(2,10),(3,11),(11,10),(3,2)]),[(1,10),(11,10),(3,2)])
        r,x,f=a.snap();nr,nx,nf=a.post['pair'];self.assertEqual({k:v for k,v in r.items() if k!='RAX'},{k:v for k,v in nr.items() if k!='RAX'});self.assertEqual(x,nx);self.assertEqual(f,nf)
    def test_off_restores_collision_detaches_and_syncs_harvest_to_physical_root(self):
        a=Machine(self);a.carry();pose=a.e['identity'].copy();pose[12:15]=[110.,201.,320.];a.put(a.e['bodies']+10*0x90,struct.pack('<16f',*pose));a.put(a.h+72,bytes(8))
        self.assertEqual(a.run('pair',[(10,1),(10,2)]),[(10,1),(10,2)]);a.run('tick');self.assertEqual(a.phase(),0);self.assertEqual(struct.unpack('<3f',a.raw(a.e['target']+0x2294,12)),(110.,201.,320.));self.assertEqual(sum(n==hex(m.CHAR_SETTER_RVA) for n,_ in a.calls),1);self.assertEqual([v[1] for n,v in a.calls if n=='0xfcda50'],[10,11])
        mark=len(a.calls);a.run('tick');self.assertEqual([n for n,_ in a.calls[mark:]],['tick'])
    def test_generation_harvest_world_and_body_reuse_reject_stale_setters(self):
        for why in ('generation','harvest','body','world'):
            with self.subTest(why=why):
                a=Machine(self);a.carry();mark=len(a.calls)
                if why=='generation':a.put32(a.local['mapping']+24,0x000ABEEE)
                elif why=='harvest':a.put32(a.e['target_source']+0x170,0)
                elif why=='body':a.put(a.e['bodies']+11*0x90+0x48,struct.pack('<Q',a.e['shapes']))
                else:a.put(a.e['physics_manager']+0x30,bytes(8))
                a.run('tick');self.assertEqual(a.phase(),0);self.assertFalse(any(n in ('0x3320e0',hex(m.CHAR_SETTER_RVA)) for n,_ in a.calls[mark:]))
    def test_unknown_floor_bones_and_large_time_delta_fail_closed(self):
        a=Machine(self);a.run('pickup');a.run('pair',[(10,2)]);self.assertEqual(a.phase(124),0)
        for _ in range(6):a.now+=200;a.put(a.h+72,struct.pack('<Q',a.now+300));a.run('tick')
        self.assertEqual(a.phase(),0);self.assertEqual(a.phase(144),6)
        a=Machine(self);a.put(a.e['head_name'],b'NONE\0');a.run('pickup');self.assertEqual(a.phase(),3);a.run('tick');self.assertEqual(a.phase(),0);self.assertEqual(a.phase(144),4);self.assertTrue(any(n=='0x69db70' for n,_ in a.calls))
        a=Machine(self);a.run('pickup');a.run('pair');a.missing_jaw=True;a.now+=16;a.run('tick');self.assertEqual(a.phase(),0);self.assertEqual(a.phase(144),4)
        a=Machine(self);a.carry();a.now+=260;a.put(a.h+72,struct.pack('<Q',a.now+300));a.run('tick');self.assertEqual(a.phase(),0)
    def test_mass_speed_override_scoped_to_live_transport_full_return_state(self):
        a=Machine(self);a.run('speed');self.assertEqual(a.snap(),a.post['speed']);a.carry();a.run('speed');r,x,f=a.snap();nr,nx,nf=a.post['speed'];self.assertEqual(r,nr);self.assertEqual(x[1:],nx[1:]);self.assertEqual(f,nf);self.assertEqual(x[0]&0xFFFFFFFF,0x3F800000)
        a.put(a.h+72,bytes(8));a.run('speed');self.assertEqual(a.snap(),a.post['speed'])
    def test_cancel_telemetry_distinguishes_reach_anchor_jump_tick_gap_and_native_link(self):
        for why,detail in (('reach',13),('jump',11),('tick_gap',8),('link',3)):
            with self.subTest(why=why):
                a=Machine(self);a.carry();a.now+=16
                if why=='reach':a.put(a.e['bodies']+11*0x90+48,struct.pack('<f',120.))
                elif why=='jump':a.put(a.e['dog_character']+0x2294,struct.pack('<f',106.))
                elif why=='tick_gap':a.now+=250;a.put(a.h+72,struct.pack('<Q',a.now+300))
                else:a.put(a.e['target']+0x650,bytes(16))
                a.run('tick');self.assertEqual(a.phase(),0);self.assertEqual(a.phase(144),2)
                self.assertEqual(a.phase(184),detail)
                if why=='reach':self.assertGreater(struct.unpack('<f',a.raw(a.h+m.STATE_OFFSET+188,4))[0],100.)
                if why=='jump':self.assertGreater(struct.unpack('<f',a.raw(a.h+m.HEADER_SIZE+200,4))[0],9.)
    def test_collision_header_race_preserves_native_output(self):
        a=Machine(self);a.carry();a.mutation=lambda v:v.put(v.h+64,struct.pack('<Q',9));self.assertEqual(a.run('pair',[(10,1),(10,2)]),[(10,1),(10,2)])
    def test_tick_publication_race_skips_only_current_setters_but_off_expiry_and_stable_identity_detach(self):
        a=Machine(self);a.carry();mark=len(a.calls);a.now+=16
        a.mutation=lambda v:v.put(v.h+64,struct.pack('<Q',9));a.run('tick')
        self.assertEqual(a.phase(),2);self.assertFalse(any(n in ('0x3320e0',hex(m.CHAR_SETTER_RVA)) for n,_ in a.calls[mark:]))
        self.assertEqual(struct.unpack('<Q',a.raw(a.h+m.HEADER_SIZE+216,8))[0],1)
        a.put(a.h+64,struct.pack('<Q',2));a.now+=16;a.run('tick');self.assertEqual(a.phase(),2)
        for why in ('off','expired','stable_identity'):
            with self.subTest(why=why):
                a=Machine(self);a.carry();a.now+=16
                if why=='stable_identity':a.put(a.e['meta']+1,b'\0')
                else:a.put(a.h+64,struct.pack('<Q',3));a.put(a.h+72,struct.pack('<Q',0 if why=='off' else 1000))
                a.run('tick');self.assertEqual(a.phase(),0);self.assertEqual(a.phase(144),2)
    def test_gate_all_classes_native_register_effect_and_lease_owner_guards(self):
        for c in (0,1,2,3,4,5,6,7,8,9,10,255):
            with self.subTest(c=c):
                a=Machine(self,c);a.run('gate');self.assertEqual(bool(a.reg('EFLAGS')&0x40),1<=c<=9);self.assertEqual(a.reg('RAX'),a.e['definition']);self.assertEqual(a.reg('RDI'),a.e['job'])
        for why in ('off','owner','generation','qpc_rebind'):
            a=Machine(self)
            if why=='off':a.put(a.h+72,bytes(8))
            elif why=='owner':a.put(a.e['meta'],b'\1')
            elif why=='generation':a.put32(a.local['mapping']+20,0x00099ABD)
            else:a.mutation=lambda v:v.put(v.h+64,struct.pack('<Q',9))
            a.run('gate');self.assertFalse(a.reg('EFLAGS')&0x40)
    def test_cancel_new_dog_and_expiry_cleanup_without_live_python_writes(self):
        for why in ('drop','dog','expiry','native_flag'):
            with self.subTest(why=why):
                a=Machine(self);a.carry()
                if why=='drop':a.put(a.e['target']+0x650,bytes(16));a.put(a.e['dog_character']+0x650,bytes(16))
                elif why=='dog':a.put(a.h+264,struct.pack('<Q',a.e['dog']+0x100))
                elif why=='native_flag':a.put(0x2000C0428,bytes(8))
                else:a.now=1301
                a.run('tick');self.assertEqual(a.phase(),0);self.assertEqual(sum(n==hex(m.CHAR_SETTER_RVA) for n,_ in a.calls),1)
                if why=='native_flag':self.assertEqual(a.phase(144),1)
    def test_native_pickup_flag_can_arrive_after_registration_without_early_drop(self):
        a=Machine(self);a.put(0x2000C0428,bytes(8));a.run('pickup');a.run('pair');a.now+=16;a.run('tick');self.assertEqual(a.phase(),1);self.assertFalse(any(n=='0x3320e0' for n,_ in a.calls))
        a.put(0x2000C0428,struct.pack('<Q',1<<47));a.now+=16;a.run('tick');self.assertEqual(a.phase(),2)
    def test_unknown_terrain_rejects_then_releases_native_attachment_without_setters(self):
        a=Machine(self);a.put(a.e['terrain'],bytes(8));a.run('pickup');self.assertEqual(a.phase(),3);self.assertEqual(a.phase(144),7)
        a.run('tick');self.assertEqual(a.phase(),0);self.assertTrue(any(n=='0x69db70' for n,_ in a.calls));self.assertFalse(any(n in ('0x3320e0',hex(m.CHAR_SETTER_RVA)) for n,_ in a.calls))

if __name__=='__main__':unittest.main()
