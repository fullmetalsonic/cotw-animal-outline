"""Execute the assembled ATV scalar hook and native effective-speed consumers."""
import hashlib
import math
import struct
import unittest
from unittest.mock import patch

import mad_max_speed as m
from test_ninja_mode import FakeAPI as BaseAPI, fixture as local_fixture, put_qword, put_u32

# Exact installed-build 1F220E..1F25B4. Physics/auto-shift entry points are
# bounded test doubles; this original body performs all torque/runtime writes
# and its complete original stack/register epilogue on both ON and OFF paths.
NATIVE_BODY=bytes.fromhex('488bd6f3410f114020488bcfe8a10300000f28d0f30f1153184084ed740bf30f104f5c410f57cbeb0e480fbe4b65488b4760f30f100c88807b0400740af30f10473c0f2fc77705f30f104754f30f59c833edc78424e0000000000000008bd5f30f59ca0f57d2f30f10d1f30f108c24e0000000f30f5fcaf30f114b1c396f787e318bcd0f1f40006666660f1f840000000000488b4770488d4904ffc2f30f104401fcf30f594320f30f11440b203b57787ce04c8bc3488bd6488bcfe8820900000f2f7b687231488b4e10488b01ff904003000084c0751b488b4e10488b01ff90a003000084c0750640386e0c7404b001eb0232c088436640386b64740bf30f10475c410f57c3eb0e480fbe4b65488b4760f30f1004880fb6430484c0740af30f104f3c0f2fcf7705f30f104f54f30f59c10f57d289ac24e0000000f30f108c24e0000000f30f594318f30f10d0f30f5fcaf30f114b1c84c0743a8b47788bd585c07e31488d4b246666660f1f840000000000f30f104b20488d4904660f6ec0ffc20f5bc0f30f5ec8f30f1149fc8b47783bd07cde892b40386b660f85ec0100004c89a424f00000004c89ac24b00000004c8b6e10440f29442470440f28c74d63a5d01200004d85e40f8e5a010000498bb5081300004c89b424a80000004881c6600200004c89bc24a00000004d8db5a01900000f29b424900000004d8dbd741d0000f30f1035f8027401440f294c2460f3440f100dd5f77701440f29542450f3440f101502157401440f29642430f3440f10256bc87401440f296c2420f3440f102dc4887401813effffff7f0f8586000000f3410f100e0f28d1f3410f59d2f3410f5f17f30f5ed10f2fd67233410f28cc0f28c2e897b248010f28c8f30f5ccef3410f59cdf30f5fcff30f5dcef30f5fcff30f5dcef3410f59c9f30f58ceeb230f28c60f28cef30f5cc2f30f5fc7f30f5dc6f30f5fc7f30f5dc6f3410f59c1f30f5cc8498b85b8120000f30f598c2894010000f3440f58c14881c6700200004983c7084983c6404881c5f00100004983ec010f854effffff440f286c2420440f28642430440f28542450440f284c24600f28b424900000004c8bbc24a00000004c8bb424a8000000807b64004c8ba424f0000000740bf30f10475c410f57c3eb0e480fbe4b65488b4760f30f100488807b0400740af30f104f3c0f2fcf7705f30f104f54498b85d01e00004c8bac24b0000000f30f59c1f30f59402cf3440f5ec0f3440f1103440f284424700f28bc2480000000440f285c24404881c4b80000005f5e5d5bc3')
NATIVE_SELECTOR=bytes.fromhex('4883ec08807c2440000f28e9440fb649214c8bc17404440249200f2f1d9f0f74014c8b5c243041c603007318f30f59595c488b442438f30f595954f30f11184883c408c34180f9010f840c010000488b41600f57e448895c24100fb65c244848893c24f30f100884db740af30f10413c0f2fc47705f30f104154488b7c2438f30f59c80f28c1f30f59c3f30f11074180f9010f8cb50000000f2fe90f87ac0000004d0fbe130f28ca488b4960450fbec941ffc9f3420f590c91f3420f5e4c9104453bd10f8d880000000f1f8000000000498b4010490fbeca0f2f048873050f2fc1726e498b4060f30f1044880484db740bf3410f10483c0f2fcc7706f3410f104854f30f59c10f2fe8774641fec2f30f59c34588130f28caf30f11074d0fbe13418d4201413bc17d11498b4860f3420f590c91f3420f5e4c9104453bd17c91488b5c2410488b3c244883c408c341c603ff488b5c2410488b3c244883c408c3cc')


# Native wheel clamp and the complete native shift helper, without physics mocks.
NATIVE_SHIFT=bytes.fromhex(
    '405556574881ecf00000004180786600498bf8f3410f104068488beaf30f5c4204440f298c2490000000488bf1450f57c9f3410f5fc1f3410f114068740b410f'
    '2fc1770541c64066004180786400740a41c6406500e928080000488b4a1048899c24100100004c89a424e80000004c89ac24e0000000488b01488b9950020000'
    '4c89b424d80000004c89bc24d00000000f29b424c00000000f29bc24b0000000440f298424a0000000440f29942480000000440f295c2470440f29642460440f'
    '29742450440f297c2440ff90080100000f108bb0050000450f57ff488b55100f28150a73db01486308488b83e00000000f59c94c8d24c949c1e4044c03632044'
    '0f28d90f28c1440fc6d9550fc6c10049634c2468440f58d80fc6c9aa48c1e107440f58d9440f10740140488bca488b02440f5cb260040000410f52cb410f28c3'
    '0f59c10f59c10f590db372db010f5cd00f59d1410f59d3450fc2df02440f55daff9020030000488b5d104533ed0f57fff3440f59d8458bf5488bcb0f28056ef1'
    '7701410f544424200f28c8488b83d01e0000f3440f10a3a41000000fc6c84e0f56c8440f28c1f3440f105030440fc6c1b1440f56c144396e787e3a458bfd6690'
    '488b4670410f28f2418bd6488bcbf3410f593407e8571c0400f30f5ef041ffc64983c704f30f58fe443b76787cd2488b5d10488bcb450f28d1488b83d01e0000'
    '458bf5f3450f59c3f3440f105840f3450f59c4f3440f119c2418010000f3440f5ec7f30f107848440f5705410374014439abd01200000f8e96000000f3440f10'
    '1d7bf873014d8bfdf3440f10257f117801488bd90f1f40000f1f840000000000410f28f6418bd6410f59742420488bcbe8bb1b0400488b46700f28ce488b5d10'
    '410f28d3f30f5ed041ffc60fc6ce550f28c60fc6c6000f58c80fc6f6aa410f28c7f3410f59d40f58ce0f5cc1f3420f5904384983c704f30f59c2f3440f58d044'
    '3bb3d01200007c98f3440f109c2418010000440f287c2440440f28742450440f2864246044386f64740ef30f104e5c0f570d7a027401eb0e480fbe4f65488b46'
    '60f30f100c880fb6570484d2740bf30f10463c410f2fc17705f30f104654f30f105f1cf30f59c80f28f30f28c3f30f59059fec7701f3410f59ca0f2fc873030f'
    '28f1f30f104708410f2fc1720ff30f5c4504f30f114708e9d1040000440f2f8bac040000440fb67e21410f96c44584e4740444027e204438ab241f00000f848c'
    '00000088542438488d8424200100004488642430410f28da48894424280f28d7488d8424180100004489ac2420010000410f28c84889442420488bce4488ac24'
    '18010000e857f9ffff0fbe8424180100003a47650f84580400008bd0450fbec741ffc884c0410fb6c8410f48d50fb6c2413bd00f4cc8884f658b4658894768c6'
    '476601c747089a99993ee923040000f30f105638410f2fd17626f30f104d000f2f0dc2087401761ff30f104504f30f5ec2f30f59c9f30f5fc1f30f114710eb07'
    'c747100000803f440fb677654584f60f8e57010000488b4660f30f105634f30f1067100f28ca4d0fbeeef3420f590ca8f3420f5e4ca8fc488b06f3420f1044a8'
    'fcf3410f5fcbf30f5dcff30f5cc1f30f59c4f30f58c10f2fd8760d410fb6de453af70f8c76010000440f2f4e3c736984d27565488b45103890261f00007459f3'
    '0f1045080f28dfc644243001410f28d04488642428488bd7488bcef30f11442420e89af9ffff33d20fb6c084c08bca410fb6de0f4fc8413acf0f8d1f01000088'
    '4f65885714c64704018b4658c747089a99993ee9fc000000f30f1045080f28dff30f5cda885424304488642428488bd7488bcef30f11442420f30f59dcf30f58'
    'da410f28d1e836f9ffff84c00fbec8ba000000000f48ca418bd6413bcd0fb6c10f4cd0807e40007420418d45ff0fbed23bd0458d4501410fb6c80f4cd0413bd0'
    '0fb6c20f4cc80fb6d1410fb6de413ad60f8488000000448877140fb6da8857658b4658c747089a99993eeb6b488b4510410fb6de4438a8261f0000746184d275'
    '5d440f2f4e3c7356f30f1045080f28dfc644243001410f28d04488642428488bd7488bcef30f11442420e891f8ffff0fb6c0418bcd84c00f4fc8413acf7d1f88'
    '4f6544886f14c6470401c747080000803f8b46580fb6d9894768c64766014c0fbef3450fbeff458d6e01453bef0f8d7d010000488b4660f30f105634f30f105f'
    '100f28caf3420f590cb0f3420f5e4cb004488b4610f3420f1004b0f3410f5fcbf30f5dcff30f5cc1f30f59c3f30f58c10f2ff00f82b40100000f2f770c0f82aa'
    '010000f3440f104d08f30f5cfac644243000488bd74488642428488bcef3440f114c2420f30f59fbf30f58fa410f28d00f28dfe8c8f7ffff41ffcf0fb6c80fbe'
    'c1443bf8410fb6d7899424180100000f4cca3acb750a807f04000f844d0100000fb6570484d2742b488b451080b8261f000000751e84c9781a884f65c6471400'
    'c64704008b4658c747089a99993ee913010000885424300f28df4488642428488bd7410f28d0f3440f114c2420488bcee84bf7ffff0fb6942418010000440fb6'
    '46400fbec8413bce410f4cce413bcf0fb6c10f4cd041ffce4584c0741a0fbed2413bd6410fb6cd410f4cd6413bd50fb6c20f4cc80fb6d13ad30f84ae00000045'
    '84c0741a0fbed2413bd6410fb6cd410f4cd6413bd50fb6c20f4cc80fb6d1885f148857658b4658c747089a99993eeb760f2ff77278807f0400488b4660f30f10'
    '00746af30f594654410f2fc0765ff30f104508418d5fffc6442430000f28df4488642428410f28d0488bd7f30f11442420488bcee887f6ffff84c00fbed0b800'
    '0000000fb6cb0f48d0c64714000fb6c23bd3c64704000f4cc8c747080000803f884f658b4658894768c6476601f30f11770c440f28942480000000440f288424'
    'a00000000f28bc24b00000000f28b424c00000004c8bbc24d00000004c8bb424d80000004c8bac24e00000004c8ba424e8000000488b9c2410010000440f285c'
    '2470440f288c24900000004881c4f00000005f5e5dc3'
)

NATIVE_WHEEL_RPM=bytes.fromhex(
    '40534883ec104c8b5210488bd933d20f57db448bda4d6382d01200004585c00f8eff0000004183f8080f82f50000004d8b8ab81200000f57e448897c24200f57'
    'ed488b7970418bc80f29342481e1070000807d07ffc983c9f8ffc10f28358e1a7801418bc02bc14863c8488bc20f1f00f3420f108408400300004183c308f342'
    '0f108c0820070000f3420f109c0850010000f3420f109408300500000f14d80f1004970f14d1f3420f108c08e00e00000f16daf3420f109408f00c00000f59d8'
    'f3420f108408000b00000f14d10f59de0f58e3f3420f109c08100900000f14d84805800f00000f104497104883c2080f16da0f59d80f59de0f58eb483bd10f8c'
    '6cffffff0f2834240f58e5488b7c24200f28dc0f12dc0f58dc0f28c30fc6c3f5f30f58d84963cb4d8bc8493bc80f8ddd000000f30f102525197801498bc0488b'
    '5370482bc14883f804498b82b81200000f8c8d0000004d8d50fd4c69c1f00100000f1f40006666660f1f840000000000f30f10548a08f3410f59940030050000'
    'f30f10448a0cf3410f59840020070000f3410f108c0040030000f30f59ccf30f58d0f3410f10840050010000f30f59c44981c0c0070000f30f594c8a04f30f59'
    '048a4883c104f30f59d4f30f58c3f30f58c8f30f58d10f28da493bca7c92493bc97d2d4c69c1f0010000f3420f108400500100004981c0f0010000f30f59c4f3'
    '0f59048a48ffc1f30f58d8493bc97cda0f28c34883c4105bc3'
)

NATIVE_SHIFT_WRAPPER=bytes.fromhex(
    '40534883ec40440fb64424780f28cb0fb659210f28e24584c07403025920807a64000f85830000000fb68424800000000f57c0f30f105a180f28d1884424380f'
    '28cc4488442430488d4424584889442428488d4424784889442420f30f11442458c644247800e835fefffff30f104424580f2f44247076230fb64424780fbec8'
    '448bc00fb6c30fbed3ffca3bca440f44c0410fb6c04883c4405bc3440fb6442478410fb6c04883c4405bc332c04883c4405bc3'
)

NATIVE_WHEEL_CLAMP=bytes.fromhex(
    '488b03488bcbff9070030000450f2fc80f28f0410f28c97304410f57ca0f2fce766e418bf64439b3d01200007e62498bfe90488babb81200004438b42fd00100'
    '00753c488b038bd6488bcbff9068030000410f2fc07628450f2fc8410f28c97304410f57caf30f10842f50010000f30f5ec1f30f59c6f30f11842f50010000ff'
    'c64881c7f00100003bb3d01200007ca2'
)

NATIVE_RATIO=bytes.fromhex(
    '4c8bd14584c0740ef30f10495c0f570d8c087401eb0c498b42604963c9f30f100c8884d27416f3410f10523c0f57c00f2fd07608f30f59d10f28c2c3f3410f59'
    '4a540f28c1c3'
)

NATIVE_GETTERS={
    0x23c7d0:bytes.fromhex('488b81d81e00004863ca488b4070f30f100488c3'),
    0x1f6b20:bytes.fromhex('488d4140c3'),
    0x235300:bytes.fromhex('488b81b01f00004885c07406f30f10400cc3f30f1005f6d36f01c3'),
    0x234a80:bytes.fromhex('4863c24869d0f0010000488b81b8120000f30f108402d8010000c3'),
}
NATIVE_CONSTANTS={
    0x1932710:bytes.fromhex('0000803f000034420000005f00000000'),
    0x19331c0:bytes.fromhex('00000080000000800000008000000080'),
    0x1933930:bytes.fromhex('0ad7233c8fc2753ccdcccc3dabaa2a3e'),
    0x1933938:bytes.fromhex('cdcccc3dabaa2a3e8dedb5a0f7c6b03e'),
    0x1971c24:bytes.fromhex('9a99593fae47613fff5b713f0000783f'),
    0x1971f40:bytes.fromhex('00000000ffffffff0000000000000000'),
    0x1974020:bytes.fromhex('ebc91841b81e1d410000484200701946'),
    0x19740b0:bytes.fromhex('ebc91841ebc91841ebc91841ebc91841'),
    0x1faa040:bytes.fromhex('00004040000040400000404000004040'),
    0x1faa050:bytes.fromhex('0000003f0000003f0000003f0000003f'),
}


# Original tire curves, evaluator, contact gate and demand clamps.
NATIVE_GRIP={
    0x2372e0:bytes.fromhex(
        '488bc4574881ecb0000000440f2940d8488bf9440f2948c8440f28c3440f2958a8450f57c9440f28da440f296098450f2ed9440f28e175080f57c0e91c020000'
        '450f2fc148899c24c00000000f29bc24a0000000440f29542470f3440f10157dbe6f01764cf30f108938060000440f2fc17710bb1805000041b968030000e9b1'
        '000000f30f10813c060000f3440f5cc1f30f5cc1bba805000041b918050000f30f5f05cdfa6f01f3440f5ec0e990000000f30f108140060000440f2fc0722e45'
        '0f2fc17304450f57c2410f2fc17304410f57c2f30f5f0599fa6f01bbf803000041b968030000f3440f5ec0eb54450f2fc17304450f57c2410f2fc10f28d07304'
        '410f57d2f30f108944060000410f2fc97304410f57ca410f2fc17304410f57c2f3440f5cc2bb88040000f30f5cc841b9f8030000f30f5f0d38fa6f01f3440f5e'
        'c1f3410f10543908488d5738418b84398c0000004c8d4710f3410f1044390cf3450f5fc1f3410f105c39044883c160894424484903c948894c24404903d1418b'
        '8c39880000004d03c1f3440f5d059eb26f014889542438410f28cb0f540dfe3870014c89442430f30f11442428f30f11542420f3410f101439e8e2ce3a01f30f'
        '10543b0c488d4f60f30f105c3b08488d57388b843b8c0000004c8d4710894424484803cb48894c24404803d38b8c3b880000004c03c34889542438410f28cb0f'
        '540d9a3870010f28f84c89442430f30f11542428f30f10143bf30f115c2420f30f105c3b04e876ce3a01450f2fd9488b9c24c0000000f30f5cc7f3410f59c0f3'
        '0f58c70f28bc24a0000000f3410f59c47304410f57c2440f285424704c8d9c24b0000000450f2843e0450f284bd0450f285bb0450f2863a0498be35fc3'
),
    0x2377e0:bytes.fromhex(
        '488bc44881ecb80000000f2978d80f28fa440f2940c8450f57c0440f2948b8440f28cb450f2ec8440f296098440f28e175080f57c0e9d0010000410f2ff84889'
        '9c24b00000000f29b424a0000000440f2954246073070f573d83b96f01450f2fc8f30f10896003000072600f2ff97727f30f5f0dd8c06f01bab0010000b84002'
        '0000450f28d1f30f5ef94c8d140a488d1c08e983000000f30f108164030000f30f5cf9f30f5cc1ba40020000b8d0020000450f28d14c8d140af30f5f058fc06f'
        '01488d1c08f30f5ef8eb4f0f2ff9488d99900000007711f30f5f0d71c06f014c8bd1f30f5ef9eb26f30f108164030000f30f5cf9f30f5cc14c8bd3488d992001'
        '0000f30f5f0546c06f01f30f5ef8450f28d1440f5715c6b86f01f3410f104a08498d5260418b828c0000004d8d4238f3410f10420c4d8d4a10f3410f105a04f3'
        '410f5ff8f3410f1012418b8a88000000894424484889542440f30f5d3dcfad6f014c894424384c894c2430f30f11442428f30f114c2420410f28cae820ca3a01'
        'f30f10530c488d5360f30f105b084c8d43388b838c0000004c8d4b108b8b88000000410f28ca894424480f28f048895424404c894424384c894c2430f30f1154'
        '2428f30f1013f30f115c2420f30f105b04e8cac93a01450f2fc8488b9c24b0000000440f28542460f30f5cc6f30f59c7f30f58c60f28b424a0000000f3410f59'
        'c473070f5705d6b76f014c8d9c24b8000000410f287bd8450f2843c8450f284bb8450f286398498be3c3'
),
    0x15e4380:bytes.fromhex(
        '4883ec680f297424500f28f10f28e30f28ea85c90f84eb00000083e901747c83f901740d0f57c00f287424504883c468c38b8424b80000000f28d4f30f108424'
        '980000000f28cdf30f109c2490000000c74424480100000089442440488b8424b00000004889442438488b8424a80000004889442430488b8424a00000004889'
        '442428f30f114424200f28c6e88f0500000f287424504883c468c38b8424b80000000f28d4f30f108424980000000f28cdf30f109c2490000000c74424480100'
        '000089442440488b8424b00000004889442438488b8424a80000004889442430488b8424a00000004889442428f30f114424200f28c6e8b50200000f28742450'
        '4883c468c38b8424b80000000f28d4f30f108424980000000f28cdf30f109c2490000000c74424400100000089442438488b8424a80000004889442430488b84'
        '24a00000004889442428f30f114424200f28c6e8280100000f287424504883c468c3'
),
    0x15e4600:bytes.fromhex(
        '0f2eca0f28e07512f30f585c2428f30f591dfaf134000f28c3c30f2fe276278b442440f30f10442428ffc80faf442448f30f5cc34863c8488b442438f30f5904'
        '88f30f58c3c30f2fe17318f30f10442428488b442438f30f5cc3f30f5900f30f58c3c38b542440f30f5ce1448b4c2448f30f5cd14c8b5424304533c0ffcaf30f'
        '5ee283fa017e2f660f1f840000000000428d0c02d1f98bc1410fafc14898410f2f248273048bd1eb03448bc18bc2412bc083f8017fda488b4424380f57c0450f'
        'afc1410fafd14963c84c63caf3410f102c8af3430f100c8af30f5ccd0f2ec87506f30f100488c3f30f100521e03400f30f5ce5f30f5ec1f3420f100c88f30f5c'
        '0c88f30f59e0f30f10442428f30f5cc3f30f59e1f30f582488f30f59e0f30f58e30f28c4c3'
),
    0x225959:bytes.fromhex(
        'f30f5983880100000f57e4488b442438f30f106c24300f57dbf30f59ab900100000f28f7f30f5e7424400f280da646d801f30f59e8'
),
    0x2259e2:bytes.fromhex(
        '410f2fe07606f30f5de5eb04f30f5fe5'
),
    0x225ae1:bytes.fromhex(
        '0f284c24600f28f8eb28450f2fd8770a410f57ff7304450f57dff3440f591d10527101f3450f5fd8f3450f5ddcf3410f59fbf3440f597424300f57db488b7c24'
        '38f30f59bb88010000450f57edf30f59bb90010000f3410f59fe'
),
    0x225cf8:bytes.fromhex(
        '410f2ff07606f30f5df7eb04f30f5ff7'
),
    0x2253f0:bytes.fromhex(
        '488b9eb81200004d69fdf00100004903df817b20ffffff7f75188b8368010000898350010000c6839c01000001e9d70b0000'
),
}
NATIVE_GRIP_CONSTANTS={
    0x1932710:bytes.fromhex('0000803f000034420000005f00000000'),
    0x19331c0:bytes.fromhex('00000080000000800000008000000080'),
    0x1933810:bytes.fromhex('0000003f9905c93ff304b56400000080'),
    0x1933930:bytes.fromhex('0ad7233c8fc2753ccdcccc3dabaa2a3e'),
    0x1936e54:bytes.fromhex('6f12833a0000003c0ad7233df168e388'),
    0x193ad14:bytes.fromhex('cdcc4c3eabaaaa3ec3b8b23e3333b33e'),
    0x193ad80:bytes.fromhex('ffffff7fffffff7fffffff7fffffff7f'),
    0x1faa030:bytes.fromhex('00000040000000400000004000000040'),
}


# Original complete native aerodynamic force calculation and its RIP constants.
NATIVE_AERO=bytes.fromhex('48895c2408574881ecb00000000f29bc24900000000f57c9410f114910498bf94883b9e004000000488bd9440f295c24500f57ff75050f57c0eb08f30f10818c0700004883b9d004000000f3440f101d9ce77001f3440f5cd80f8402020000440f2f1da9f970010f82f4010000488b010f29b424a0000000440f29842480000000440f294c2470440f29642440440f29742430450f107040440f5cb180040000440f297c2420440f107a10410f28ce0f594a200f590dd6ae71010f28f10f28c10fc6c1000fc6f1550fc6c9aa0f58f00f58f1410f28cf410f59ce440f28c10f28c10fc6c100440fc6c1550fc6c9aa440f58c0440f58c1410f28ce0f590a440f28c90f28c1440fc6c9550fc6c100440f58c80fc6c9aa440f58c9ff9040020000488b8bd0040000f30f1019f3440f10610484c0742a410f28ec0f28c6f30f596910410f28cbf30f590da4f77001f30f59c6f30f59cbf30f59e8f30f59e9eb030f57ed0f2ff7440f295424600f28e6f3440f10152af17001410f57e272050f28d6eb030f28d4f30f5c93bc040000f30f104908f30f591d0ff97001f30f10410cf30f5e15d27a3802f30f5cc1f30f5fd7f30f5d153ae67001f30f59d0f30f58d1f30f59d3f30f59d9f3410f59d4f3410f59dc440f2864244073030f28f4440f2fcf7304450f57ca440f2fc77304450f57c2440f285424600f28cbf3410f59c90f28c5440f284c2470f30f59f2f30f590d8af87001f3410f59d8440f28842480000000f30f58ce0f28b424a0000000f30f591d04f870010fc6c000410f59c7440f287c2420f30f58cbf3410f59cb0fc6c900410f59ce440f287424300f58c80f110feb04410f11094c8d9c24b0000000498b5b10410f287be0450f285ba0498be35fc3')
NATIVE_AERO_CONSTANTS={
    0x1932710:bytes.fromhex('0000803f000034420000005f00000000'),
    0x1933930:bytes.fromhex('0ad7233c8fc2753ccdcccc3dabaa2a3e'),
    0x193eeb0:bytes.fromhex('000080bf000080bf000080bf000080bf'),
    0x1933810:bytes.fromhex('0000003f9905c93ff304b56400000080'),
    0x19331c0:bytes.fromhex('00000080000000800000008000000080'),
    0x19339c8:bytes.fromhex('000000bfbd378635ffe6db2e00000000'),
    0x25abb98:bytes.fromhex('00000040c3f5a83ea8c5974101000000'),
    0x19339bc:bytes.fromhex('0000c03f0000204017b7d138000000bf'),
    0x1933958:bytes.fromhex('00004040000080400000c040f9021550'),
}


class FakeAPI(BaseAPI):
    def __init__(self):
        super().__init__()
        for rva,data in m.SIGNATURES.items():self.put(self.base+rva,data)
        for rva,data in zip((m.SITE_RVA,m.TORQUE_SITE_RVA,m.WHEEL_LIMIT_SITE_RVA)+m.GRIP_SITES+(m.AERO_SITE_RVA,),m.ORIGINALS):self.put(self.base+rva,data)

    def write(self,address,data):
        if ((address==self.base+m.SITE_RVA and self.failure=='speed_partial')
                or (address==self.base+m.TORQUE_SITE_RVA and self.failure=='torque_partial')
                or (address==self.base+m.WHEEL_LIMIT_SITE_RVA and self.failure=='wheel_limit_partial')
                or (address==self.base+m.GRIP_SITES[0] and self.failure=='long_grip_partial')
                or (address==self.base+m.GRIP_SITES[1] and self.failure=='lat_grip_partial')
                or (address==self.base+m.AERO_SITE_RVA and self.failure=='aero_partial')):
            self.events.append(('write',address,len(data)))
            self.failure=None;self.put(address,data[:3]);raise OSError('partial speed patch')
        super().write(address,data)

    def flush(self,address,size):
        super().flush(address,size)
        if ((address==self.base+m.SITE_RVA and self.failure=='speed_flush')
                or (address==self.base+m.TORQUE_SITE_RVA and self.failure=='torque_flush')
                or (address==self.base+m.WHEEL_LIMIT_SITE_RVA and self.failure=='wheel_limit_flush')
                or (address==self.base+m.GRIP_SITES[0] and self.failure=='long_grip_flush')
                or (address==self.base+m.GRIP_SITES[1] and self.failure=='lat_grip_flush')
                or (address==self.base+m.AERO_SITE_RVA and self.failure=='aero_flush')):
            self.failure=None;raise OSError('speed cache flush')


def fixture(api,mounted=True):
    game,binding,extra=local_fixture(api,mounted=mounted)
    extra['pfx']=0x200060000
    put_qword(api,extra['vehicle']+0x4A98,extra['pfx'])
    put_qword(api,extra['pfx'],api.base+m.PFX_VTABLE_RVA)
    api.put(extra['pfx']+0x2DC,struct.pack('<f',60.))
    api.put(extra['pfx']+0x2E0,struct.pack('<f',60.))
    api.put(extra['pfx']+0x4BC,struct.pack('<f',60./3.6))
    extra['transmission']=0x200070000
    put_qword(api,extra['pfx']+0x1ED8,extra['transmission'])
    t=extra['transmission']
    put_qword(api,t+0x60,t+0x100);put_u32(api,t+0x68,5)
    api.put(t+0x20,b'\0\5')
    for offset,value in ((0x3C,-1.),(0x54,8.014),(0x5C,3.)):
        api.put(t+offset,struct.pack('<f',value))
    api.put(t+0x100,struct.pack('<5f',2.231,1.8,1.529,1.278,1.048))
    return game,binding,extra


class Tests(unittest.TestCase):
    def setUp(self):
        p=patch.object(m.probe,'EXPECTED_SHA256',hashlib.sha256(b'fake ninja game').hexdigest())
        p.start();self.addCleanup(p.stop)

    def test_current_driver_read_helpers_install_off_reuse_and_eight_byte_restore(self):
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api)
        self.assertEqual(mode.publish(),1);binding=mode._binding()
        self.assertEqual(binding['pfx'],e['pfx']);self.assertEqual(binding['speed_bits'],struct.pack('<f',60.))
        self.assertEqual(api.read(mode.site,8),mode._patched(mode.allocation))
        self.assertEqual(api.read(mode.allocation+m.CODE_SIZE+72,8),struct.pack('<Q',1300))
        other=m.MadMaxSpeedMode(game,2,api=api);other.install();self.assertEqual(other.allocation,mode.allocation)
        other.publish();other.disable();self.assertEqual(api.read(other.allocation+m.CODE_SIZE+72,8),bytes(8))
        other.close();other.close();self.assertEqual(tuple(api.read(site,len(raw)) for site,raw in zip(mode.sites,m.ORIGINALS)),m.ORIGINALS)
        self.assertEqual(api.read(e['pfx']+0x2DC,4),struct.pack('<f',60.))
        self.assertFalse(any(event[0]=='free' for event in api.events))

    def test_unmounted_waits_and_bad_physics_or_speed_refuse_without_game_tuning_writes(self):
        api=FakeAPI();game,b,e=fixture(api,mounted=False);mode=m.MadMaxSpeedMode(game,1,api=api)
        with self.assertRaises(m.TransientMadMaxState):mode.publish()
        self.assertFalse(api.events)
        for value in (float('nan'),float('inf'),-1.,0.,301.):
            api=FakeAPI();game,b,e=fixture(api);api.put(e['pfx']+0x2DC,struct.pack('<f',value));mode=m.MadMaxSpeedMode(game,1,api=api)
            with self.assertRaises(RuntimeError):mode.publish()
            self.assertFalse(api.events)
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
        with patch.object(mode._local,'_binding',side_effect=m.TransientNinjaState('player changed')):
            with self.assertRaises(m.TransientMadMaxState):mode.publish()
        self.assertEqual(api.read(mode.allocation+m.CODE_SIZE+72,8),bytes(8))

    def test_wrong_executable_native_signature_or_owned_header_refuse(self):
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api)
        game.exe.read_bytes=lambda:b'unsupported executable'
        with self.assertRaises(RuntimeError):mode.publish()
        self.assertFalse(api.events)
        game.exe.read_bytes=lambda:b'fake ninja game';api.put(api.base+0x255F26,b'\0')
        with self.assertRaises(RuntimeError):mode.publish()
        self.assertFalse(api.events)
        api.put(api.base+0x255F26,m.SIGNATURES[0x255F26]);mode.publish()
        api.put(mode.allocation+m.CODE_SIZE+192,bytes(32))
        with self.assertRaises(RuntimeError):mode.publish()
        self.assertEqual(api.read(mode.allocation+m.CODE_SIZE+72,8),bytes(8))

    def test_install_close_partial_flush_context_and_lease_failures_restore_before_resume(self):
        for uninstall in (False,True):
            for why in ('speed_partial','speed_flush','torque_partial','torque_flush','wheel_limit_partial','wheel_limit_flush',
                        'long_grip_partial','long_grip_flush','lat_grip_partial','lat_grip_flush','aero_partial','aero_flush','context'):
                with self.subTest(uninstall=uninstall,why=why):
                    api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api)
                    if uninstall:mode.publish()
                    before=tuple(api.read(site,len(raw)) for site,raw in zip(mode.sites,m.ORIGINALS));api.failure=why
                    with self.assertRaises((RuntimeError,OSError)):mode.close() if uninstall else mode.install()
                    self.assertEqual(tuple(api.read(site,len(raw)) for site,raw in zip(mode.sites,m.ORIGINALS)),before);self.assertEqual(api.events[-1],('resume',))
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish();api.failure='publish'
        with self.assertRaises(OSError):mode.publish()
        self.assertEqual(api.read(mode.allocation+m.CODE_SIZE+72,8),bytes(8))
        api.put(mode.site,b'\x90'*8)
        with self.assertRaises(RuntimeError):mode.publish()

    def execute(self,condition=None,cycles=1):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
        uc=Uc(UC_ARCH_X86,UC_MODE_64)
        for address,size in ((api.base,0x3000000),(mode.allocation,m.ALLOCATION_SIZE),(0x200000000,0x100000),(0x300000000,0x10000)):uc.mem_map(address,size)
        for address,value in api.memory.items():uc.mem_write(address,bytes([value]))
        header=mode.allocation+m.CODE_SIZE;pfx=e['pfx'];site=mode.site;continuation=site+8
        qpc,constant=api.base+0x1000,api.base+0x1080
        uc.mem_write(api.base+m.QPC_IAT_RVA,struct.pack('<Q',qpc));uc.mem_write(qpc,b'\xc3')
        uc.mem_write(constant,struct.pack('<f',1./3.6))
        # Exact native 255F8D..255FA5 consumer instructions, with RIP fixup only.
        consumer=bytes.fromhex('f30f118fe0020000f30f590d')+struct.pack('<i',constant-(continuation+16))+bytes.fromhex('f30f118fbc040000')
        uc.mem_write(continuation,consumer);stop=continuation+len(consumer)
        def put(a,data):uc.mem_write(a,data)
        def u32(a,v):put(a,struct.pack('<I',v))
        if condition=='off':put(header+72,bytes(8))
        if condition=='expired':put(header+72,struct.pack('<Q',1000))
        if condition=='odd':put(header+64,struct.pack('<Q',3))
        if condition=='bad_pfx_vtable':put(pfx,bytes(8))
        if condition=='base_changed':put(pfx+0x2DC,struct.pack('<f',50.))
        if condition=='world_loading':u32(e['world']+0x48,1)
        if condition=='pool_replaced':put(e['entities']+0x20290,bytes(8))
        if condition=='player_generation':u32(b['mapping']+12,0x00071235)
        if condition=='player_inactive':u32(b['source']+0x17C,0)
        if condition=='canonical_player_changed':put(e['local_slot']+0x170,bytes(8))
        if condition=='controller_changed':put(b['player']+0x68,bytes(8))
        if condition=='vehicle_generation':u32(b['mapping']+16,0x00085679)
        if condition=='vehicle_driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
        if condition=='vehicle_inactive':u32(e['vehicle_source']+0x17C,0)
        if condition=='vehicle_type_changed':u32(e['vehicle']+0x5020,1)
        if condition=='physics_replaced':put(e['vehicle']+0x4A98,bytes(8))
        registers=('RAX','RCX','RDX','R8','R9','R10','R11','RBX','RBP','RSI','RDI','R12','R13','R14','R15')
        snapshots=[];qpcs=[];writes=[]
        def snapshot():return ([uc.reg_read(getattr(x,'UC_X86_REG_'+n)) for n in registers],[uc.reg_read(getattr(x,'UC_X86_REG_XMM'+str(i))) for i in range(16)],uc.reg_read(x.UC_X86_REG_EFLAGS))
        def trace(machine,address,size,_):
            if address==stop:uc.emu_stop();return
            if address==continuation:snapshots.append(snapshot());return
            if address!=qpc:return
            self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP)%16,8);qpcs.append(address);late=len(qpcs)%2==0
            put(uc.reg_read(x.UC_X86_REG_RCX),struct.pack('<Q',1300 if late and condition=='late_expiry' else 1000))
            for i,n in enumerate(registers[:7]):uc.reg_write(getattr(x,'UC_X86_REG_'+n),0xBAD000+i)
            for i in range(6):uc.reg_write(getattr(x,'UC_X86_REG_XMM'+str(i)),0xBAD000+i)
            uc.reg_write(x.UC_X86_REG_EFLAGS,0x246);uc.reg_write(x.UC_X86_REG_RAX,0 if condition=='qpc_fail' else 1)
            if condition=='epoch_race' or late and condition=='late_epoch_race':put(header+64,struct.pack('<Q',8))
            if late and condition=='late_driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
            if condition=='restore_site':put(site,m.ORIGINAL)
        uc.hook_add(UC_HOOK_CODE,trace)
        uc.hook_add(UC_HOOK_MEM_WRITE,lambda machine,access,address,size,value,_:writes.append((machine.reg_read(x.UC_X86_REG_RIP),address,size)))
        results=[]
        for cycle in range(cycles):
            if condition=='off_after_first' and cycle:put(header+72,bytes(8))
            for i,n in enumerate(registers):uc.reg_write(getattr(x,'UC_X86_REG_'+n),0xABC000+i)
            uc.reg_write(x.UC_X86_REG_RDI,pfx+0x1000 if condition=='other_pfx' else pfx)
            if condition=='other_pfx':put(pfx+0x1000+0x2DC,struct.pack('<f',60.))
            for i in range(16):uc.reg_write(getattr(x,'UC_X86_REG_XMM'+str(i)),(0x12345678<<80)+i)
            actual_pfx=pfx+0x1000 if condition=='other_pfx' else pfx
            uc.reg_write(x.UC_X86_REG_EFLAGS,0x203);uc.reg_write(x.UC_X86_REG_RSP,0x300008000)
            before=snapshot();uc.emu_start(site,0,count=20000)
            expected=[list(before[0]),list(before[1]),before[2]]
            base=50. if condition=='base_changed' else 60.
            active=condition in (None,'off_after_first','restore_site') and not (condition=='off_after_first' and cycle)
            expected[1][1]=int.from_bytes(struct.pack('<f',base*(2 if active else 1)),'little')
            self.assertEqual(snapshots[-1],tuple(expected));self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP),0x300008000)
            effective=struct.unpack('<f',uc.mem_read(actual_pfx+0x2E0,4))[0]
            limiter=struct.unpack('<f',uc.mem_read(actual_pfx+0x4BC,4))[0]
            self.assertAlmostEqual(effective,base*(2 if active else 1),places=5)
            self.assertAlmostEqual(limiter,effective/3.6,places=4)
            self.assertEqual(bytes(uc.mem_read(pfx+0x2DC,4)),struct.pack('<f',base))
            results.append(effective)
        allowed_native=(pfx+0x2E0,pfx+0x4BC,pfx+0x1000+0x2E0,pfx+0x1000+0x4BC)
        self.assertTrue(all(0x300000000<=a<a+n<=0x300008000 or header+256<=a<a+n<=header+360 and a!=header+312
                            or continuation<=pc<stop and a in allowed_native
                            for pc,a,n in writes),writes)
        api.put(header,bytes(uc.mem_read(header,m.HEADER_SIZE)))
        return mode.read_stats(),results

    def test_sixty_to_120_kph_native_limiter_33_ms_without_cumulative_scaling_and_off_restore(self):
        stats,results=self.execute(cycles=3);self.assertEqual(results,[120.]*3);self.assertEqual(stats['scaled'],3)
        stats,results=self.execute('off_after_first',cycles=2);self.assertEqual(results,[120.,60.]);self.assertEqual(stats['scaled'],1)
        _,results=self.execute('restore_site');self.assertEqual(results,[120.])

    def test_off_transition_foreign_driver_generation_identity_and_qpc_fail_closed(self):
        for why in ('off','expired','odd','bad_pfx_vtable','base_changed','world_loading','pool_replaced',
                    'player_generation','player_inactive','canonical_player_changed','controller_changed',
                    'vehicle_generation','vehicle_driver_changed','vehicle_inactive','vehicle_type_changed',
                    'physics_replaced','other_pfx','qpc_fail','epoch_race','late_expiry','late_epoch_race','late_driver_changed'):
            with self.subTest(why=why):
                stats,results=self.execute(why);self.assertEqual(stats['scaled'],0)

    def transmission(self,*,torque=17.5,gear=0,reverse=False,low=False,low_final=-1.,
                     condition=None,pattern=(True,),ratio=None,clutch=False,wheel_rpm=100.,full_native=False):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
        uc=Uc(UC_ARCH_X86,UC_MODE_64)
        for address,size in ((api.base,0x3000000),(mode.allocation,m.ALLOCATION_SIZE),(0x200000000,0x100000),(0x300000000,0x10000)):
            uc.mem_map(address,size)
        for address,value in api.memory.items():uc.mem_write(address,bytes([value]))
        header=mode.allocation+m.CODE_SIZE;pfx=e['pfx'];t=e['transmission'];runtime=t+0x80
        params,engine,distribution=0x200078000,0x200074000,0x20007A000
        def put(a,data):uc.mem_write(a,data)
        def q(a,v):put(a,struct.pack('<Q',v))
        def u32(a,v):put(a,struct.pack('<I',v))
        def f(a,v):put(a,struct.pack('<f',v))
        def getf(a):return struct.unpack('<f',uc.mem_read(a,4))[0]
        q(pfx+0x1ED0,engine);f(engine+0x2C,17.5)
        for off,value in ((0x40,2000.),(0x44,5000.),(0x48,6850.)):f(engine+off,value)
        q(params+0x10,pfx);f(pfx+0x1EE4,torque);put(pfx+0x1EE0,bytes([reverse]))
        put(runtime+0x64,bytes([reverse,gear,clutch]));put(runtime+4,bytes([low]));f(runtime+0x68,1.)
        f(t+0x3C,low_final);q(t+0x70,distribution);u32(t+0x78,4)
        put(distribution,struct.pack('<4f',.25,.25,.25,.25))
        u32(pfx+0x12D0,4);q(pfx+0x1308,0x200090000);q(pfx+0x12B8,0x200080000)
        if ratio is not None:f(t+0x100+gear*4,ratio)
        if condition=='bad_final':f(t+0x54,float('inf'))
        if condition=='tiny_final':f(t+0x54,2**-126)
        if condition=='transmission_replaced':q(pfx+0x1ED8,t+0x1000)
        if condition=='other_config':q(header+384,t+0x1000)
        if condition=='vehicle_driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
        if condition=='vehicle_generation':u32(b['mapping']+16,0x00085679)
        if condition=='dismounted':u32(e['vehicle_source']+0x54,0)
        if condition=='world_loading':u32(e['world']+0x48,1)
        if condition=='other_input':q(params+0x10,pfx+0x1000)
        if condition=='other_input':f(pfx+0x1000+0x1EE4,torque);q(pfx+0x1000+0x1ED0,engine)
        qpc=api.base+0x1000;q(api.base+m.QPC_IAT_RVA,qpc);put(qpc,b'\xc3')
        put(api.base+0x1E5DB0,m.SIGNATURES[0x1E5DB0])
        put(api.base+m.NATIVE_PREFIX_RVA,m.SIGNATURES[m.NATIVE_PREFIX_RVA]);put(api.base+m.NATIVE_CONTINUATION_RVA,NATIVE_BODY)
        self.assertTrue(NATIVE_BODY.startswith(m.SIGNATURES[m.NATIVE_CONTINUATION_RVA]))
        put(api.base+0x19331C0,struct.pack('<I',0x80000000))
        for address in (0x1F25C0,0x1F2C50):put(api.base+address,b'\xc3')
        if full_native:
            for rva,data in ((0x1F25C0,NATIVE_WHEEL_RPM),(0x1F2C50,NATIVE_SHIFT),
                             (0x1F2AD0,NATIVE_SHIFT_WRAPPER),(0x1F2970,NATIVE_SELECTOR)):
                put(api.base+rva,data)
            for rva,data in NATIVE_CONSTANTS.items():put(api.base+rva,data)
            # Original body-id, wheel-radius and vehicle coefficient getters.
            for slot,rva in ((0x108,0x1F6B20),(0x320,0x235300)):
                q(api.base+m.PFX_VTABLE_RVA+slot,api.base+rva)
            for rva,data in NATIVE_GETTERS.items():put(api.base+rva,data)
            q(pfx+0x1FB0,0x2000E0000);f(0x2000E0000+0xC,1.)
            q(pfx+0x250,0x2000B0000);u32(pfx+0x40,0)
            q(0x2000B0000+0x20,0x2000C0000);q(0x2000B0000+0xE0,0x2000D0000)
            put(0x2000B0000+0x5B0,struct.pack('<4f',0.,-9.81,0.,0.))
            u32(0x2000C0000+0x68,0);put(0x2000C0000+0x20,struct.pack('<4f',0.,1.,0.,0.))
            omega=wheel_rpm/struct.unpack('<f',NATIVE_CONSTANTS[0x1974020][:4])[0]
            put(0x2000D0000+0x40,struct.pack('<4f',0.,-omega*.31,0.,0.))
            f(pfx+0x10A4,125.);f(engine+0x30,15.75)
            q(t,t+0x200);q(t+0x10,t+0x300)
            put(t+0x200,struct.pack('<4f',3840.82,4044.44,3976.83,3902.60))
            put(t+0x300,struct.pack('<4f',*([6800.]*4)))
            f(t+0x34,2000.);f(t+0x38,-1.);f(t+0x58,.2);put(t+0x40,b'\1\0')
            f(params,1.);f(params+4,1./60.);f(params+8,6850.)
            f(runtime+8,-1.);f(runtime+0xC,0.);f(runtime+0x10,1.)
            for index in range(4):
                f(0x200080000+index*0x1F0+0x150,omega)
                f(0x200080000+index*0x1F0+0x1D8,.31)
        stop=mode.sites[1]+5;qpcs=[];calls=[];results=[];writes=[];configs=[]
        cfg=bytes(uc.mem_read(t,0x80));tables=bytes(uc.mem_read(t+0x100,20));original_engine=bytes(uc.mem_read(engine,0x64))
        nonvolatile=('RBX','RBP','RSI','RDI','R12','R13','R14','R15')
        def shadow():
            sp=uc.reg_read(x.UC_X86_REG_RSP);self.assertEqual(sp%16,8);put(sp+8,b'\xCC'*32)
        def trace(machine,address,size,_):
            if address==stop:machine.emu_stop();return
            if address in (api.base+m.NATIVE_PREFIX_RVA,mode.allocation+m.ADAPTER_ENTRY):
                self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP)%16,8)
                self.assertEqual(uc.reg_read(x.UC_X86_REG_R8),runtime)
                calls.append('adapted' if address==mode.allocation+m.ADAPTER_ENTRY else 'original')
                if condition=='restore_site':
                    put(mode.sites[1],m.TORQUE_ORIGINAL)
                    uc.ctl_remove_cache(mode.sites[1],mode.sites[1]+5)  # NativeAPI.flush equivalent.
            if address in (api.base+0x1F25C0,api.base+0x1F2C50):
                shadow();config=uc.reg_read(x.UC_X86_REG_RCX)
                self.assertEqual(uc.reg_read(x.UC_X86_REG_RDX),params)
                active=calls[-1]=='adapted'
                if active:self.assertTrue(0x300000000<=config<0x300008000)
                else:self.assertEqual(config,t)
                expected=bytearray(cfg)
                if active:
                    struct.pack_into('<f',expected,0x54,getf(t+0x54)*.5)
                    if low_final>0:struct.pack_into('<f',expected,0x3C,low_final*.5)
                self.assertEqual(bytes(uc.mem_read(config,0x80)),bytes(expected))
                self.assertEqual(bytes(uc.mem_read(pfx+0x1EE4,4)),struct.pack('<f',torque))
                configs.append(getf(config+0x54))
                if address==api.base+0x1F2C50:
                    self.assertEqual(uc.reg_read(x.UC_X86_REG_R8),runtime)
                elif not full_native:
                    uc.reg_write(x.UC_X86_REG_XMM0,int.from_bytes(struct.pack('<f',wheel_rpm),'little'))
                    if condition=='off_in_native':q(header+72,0)
                return
            if address!=qpc:return
            shadow();qpcs.append(address);late=len(qpcs)%2==0
            q(uc.reg_read(x.UC_X86_REG_RCX),1300 if late and condition=='late_expiry' else 1000)
            for n in ('RAX','RCX','RDX','R8','R9','R10','R11'):uc.reg_write(getattr(x,'UC_X86_REG_'+n),0xBAD000)
            for i in range(6):uc.reg_write(getattr(x,'UC_X86_REG_XMM'+str(i)),0xDEAD000+i)
            uc.reg_write(x.UC_X86_REG_RAX,0 if condition=='qpc_fail' else 1)
            if late and condition=='late_owner_change':u32(e['vehicle_source']+0x54,b['handle']+1)
            if late and condition=='late_sequence':q(header+64,8)
        uc.hook_add(UC_HOOK_CODE,trace)
        uc.hook_add(UC_HOOK_MEM_WRITE,lambda machine,access,a,n,v,_:writes.append((machine.reg_read(x.UC_X86_REG_RIP),a,n)))
        for active in pattern:
            q(header+72,1300 if active else 0)
            for index,name in enumerate(nonvolatile):uc.reg_write(getattr(x,'UC_X86_REG_'+name),0xABC000+index)
            uc.reg_write(x.UC_X86_REG_RDI,pfx)
            saved={name:uc.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in nonvolatile}
            for i in range(6,16):uc.reg_write(getattr(x,'UC_X86_REG_XMM'+str(i)),(0x12345678<<80)+i)
            xmm=[uc.reg_read(getattr(x,'UC_X86_REG_XMM'+str(i))) for i in range(6,16)]
            uc.reg_write(x.UC_X86_REG_RCX,t);uc.reg_write(x.UC_X86_REG_RDX,params)
            uc.reg_write(x.UC_X86_REG_RSP,0x300008000)
            uc.emu_start(mode.sites[1],0,count=30000)
            self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP),0x300008000)
            for name,value in saved.items():self.assertEqual(uc.reg_read(getattr(x,'UC_X86_REG_'+name)),value)
            self.assertEqual([uc.reg_read(getattr(x,'UC_X86_REG_XMM'+str(i))) for i in range(6,16)],xmm)
            self.assertEqual(bytes(uc.mem_read(t,0x80)),cfg);self.assertEqual(bytes(uc.mem_read(t+0x100,20)),tables)
            self.assertEqual(bytes(uc.mem_read(engine,0x64)),original_engine)
            self.assertEqual(bytes(uc.mem_read(pfx+0x1EE4,4)),struct.pack('<f',torque))
            wheel=getf(runtime+0x20);result=(wheel,getf(runtime+0x1C),calls[-1])
            if full_native:result+=(uc.mem_read(runtime+0x65,1)[0],getf(runtime+0x18))
            results.append(result)
            for index in range(4):
                value=getf(runtime+0x24+4*index)
                if math.isnan(wheel):self.assertTrue(math.isnan(value))
                else:self.assertEqual(value,struct.unpack('<f',struct.pack('<f',wheel*.25))[0])
        self.assertEqual(len(calls),len(pattern));self.assertEqual(len(configs),2*len(pattern))
        # The original callee spills into its caller-provided 32-byte home area.
        unexpected=[(hex(pc),hex(a),n) for pc,a,n in writes
                    if not (0x300000000<=a<a+n<=0x300008020 or runtime<=a<a+n<=runtime+0x70
                            or header+256<=a<a+n<=header+360 and a!=header+312
                            or header+392<=a<a+n<=header+404)]
        self.assertEqual(unexpected,[])
        api.put(header,bytes(uc.mem_read(header,m.HEADER_SIZE)))
        return mode.read_stats(),results

    def test_five_native_gears_forward_reverse_twice_drive_and_half_clutch_rpm_with_raw_engine_unchanged(self):
        for gear in range(5):
            for reverse in (False,True):
                with self.subTest(gear=gear,reverse=reverse):
                    stats,values=self.transmission(gear=gear,reverse=reverse,pattern=(False,True,False,True))
                    baseline=values[0][0]
                    self.assertEqual([v[0] for v in values],[baseline,baseline*2,baseline,baseline*2])
                    self.assertEqual(values[1][1],values[0][1]*.5)
                    self.assertEqual([v[2] for v in values],['original','adapted','original','adapted'])
                    self.assertEqual(stats['original_torque'],17.5);self.assertEqual(stats['torque_output'],70.)
                    self.assertEqual(stats['wheel_torque'],values[-1][0])
                    _,twice_speed=self.transmission(gear=gear,reverse=reverse,wheel_rpm=200.)
                    self.assertEqual(twice_speed[0][1],values[0][1])

    def test_engine_braking_low_range_clutch_zero_and_nonfinite_overflow_policies(self):
        for reverse in (False,True):
            stats,values=self.transmission(torque=-17.5,reverse=reverse,pattern=(False,True))
            self.assertEqual(values[0][0],values[1][0]);self.assertEqual(stats['torque_output'],-35.)
        for low_final in (-1.,4.):
            stats,values=self.transmission(low=True,low_final=low_final,pattern=(False,True))
            self.assertEqual(values[1][0],values[0][0]*2)
        stats,values=self.transmission(clutch=True);self.assertEqual(values[0][0],0.);self.assertEqual(stats['wheel_torque'],0.)
        for value in (-0.,0.,float('inf'),float('-inf'),float('nan'),2**126,-2**127,2**-140):
            with self.subTest(value=value):
                stats,values=self.transmission(torque=value,pattern=(False,True))
                if math.isnan(values[0][0]):self.assertTrue(math.isnan(values[1][0]))
                else:self.assertEqual(values[0][0],values[1][0])
                self.assertEqual(stats['torque_scaled'],1 if value==0 else 0)
        stats,values=self.transmission(torque=25.,ratio=1e36,pattern=(False,True))
        self.assertTrue(math.isfinite(values[0][0]));self.assertEqual(values[0][0],values[1][0]);self.assertEqual(stats['torque_scaled'],0)

    def test_transmission_owner_expiry_dismount_and_midcall_off_use_one_consistent_native_call(self):
        for condition in ('transmission_replaced','other_config','vehicle_driver_changed','vehicle_generation','world_loading',
                          'late_expiry','late_owner_change','late_sequence','qpc_fail','bad_final','tiny_final','other_input','dismounted'):
            with self.subTest(condition=condition):
                stats,values=self.transmission(condition=condition)
                self.assertEqual(values[0][2],'original');self.assertEqual(stats['torque_scaled'],0)
        stats,values=self.transmission(condition='off_in_native',pattern=(True,False))
        self.assertEqual(values[0][0],values[1][0]*2)
        _,values=self.transmission(condition='restore_site',pattern=(True,True))
        self.assertEqual(values[0][0],values[1][0]*2);self.assertEqual([v[2] for v in values],['adapted','original'])

    def test_adapter_matches_every_original_prefix_instruction_branch_and_rip_operand(self):
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_JUMP
        from capstone.x86_const import X86_OP_MEM,X86_REG_RIP
        md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
        code=m.Path(m.__file__).with_suffix('.bin').read_bytes()
        original=list(md.disasm(m.SIGNATURES[m.NATIVE_PREFIX_RVA],m.NATIVE_PREFIX_RVA))
        adapted=[];extra=[];end=None
        for i in md.disasm(code[m.ADAPTER_ENTRY:],m.ADAPTER_ENTRY):
            if i.mnemonic=='jmp' and i.operands[0].type==X86_OP_MEM:
                end=i.address
                self.assertEqual(i.address+i.size+i.operands[0].mem.disp,m.CODE_SIZE+368)
                break
            if i.mnemonic=='mulss' and i.op_str=='xmm0, dword ptr [rsp + 0x1c8]':extra.append(i)
            else:adapted.append(i)
        self.assertEqual(len(extra),1);self.assertIsNotNone(end)
        self.assertEqual(extra[0].address,adapted[-1].address+adapted[-1].size)
        def canonical(instructions,finish,is_adapter):
            indices={i.address:n for n,i in enumerate(instructions)};result=[]
            for i in instructions:
                self.assertNotEqual(i.mnemonic,'call')
                if i.group(CS_GRP_JUMP):
                    target=i.operands[0].imm
                    result.append((i.mnemonic,'continuation' if target==finish else indices[target]))
                elif any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP for o in i.operands):
                    self.assertEqual(i.mnemonic,'movss');self.assertTrue(i.op_str.startswith('xmm11,'))
                    if is_adapter:
                        o=i.operands[-1];address=i.address+i.size+o.mem.disp
                        self.assertEqual(code[address:address+4],struct.pack('<I',0x80000000))
                    result.append(('movss','xmm11, exact sign mask'))
                else:result.append((i.mnemonic,i.op_str))
            return result
        self.assertEqual(canonical(original,m.NATIVE_CONTINUATION_RVA,False),canonical(adapted,end,True))

    def test_original_auto_shift_selector_preserves_all_five_gears_at_twice_wheel_speed(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        base=0x140000000;t=0x200000000;sp=0x300008000;stop=base+0x1000
        uc=Uc(UC_ARCH_X86,UC_MODE_64)
        for address,size in ((base,0x2000000),(t,0x10000),(0x300000000,0x10000)):uc.mem_map(address,size)
        def put(a,data):uc.mem_write(a,data)
        def q(a,v):put(a,struct.pack('<Q',v))
        def f(a,v):put(a,struct.pack('<f',v))
        put(base+0x1F2970,NATIVE_SELECTOR);put(base+0x1933930,bytes.fromhex('0ad7233c'))
        q(t+0x60,t+0x100);q(t,t+0x200);q(t+0x10,t+0x300);put(t+0x20,b'\0\5')
        put(t+0x100,struct.pack('<5f',2.231,1.8,1.529,1.278,1.048))
        put(t+0x200,struct.pack('<4f',3840.82,4044.44,3976.83,3902.60));put(t+0x300,struct.pack('<4f',*([6800.]*4)))
        f(t+0x3C,-1.);f(t+0x5C,3.)
        writes=[];uc.hook_add(UC_HOOK_MEM_WRITE,lambda machine,access,a,n,v,_:writes.append((a,n)))
        uc.hook_add(UC_HOOK_CODE,lambda machine,a,n,_:machine.emu_stop() if a==stop else None)
        seen=set()
        for wheel in range(50,951,25):
            values=[]
            for scale in (1.,.5):
                f(t+0x54,8.014*scale);q(sp-8,stop);q(sp+0x20,t+0x400);q(sp+0x28,t+0x404)
                put(sp+0x30,bytes(16));uc.reg_write(x.UC_X86_REG_RSP,sp-8);uc.reg_write(x.UC_X86_REG_RCX,t)
                for register,value in ((x.UC_X86_REG_XMM1,0.),(x.UC_X86_REG_XMM2,6850.),(x.UC_X86_REG_XMM3,wheel/scale)):
                    uc.reg_write(register,int.from_bytes(struct.pack('<f',value),'little'))
                uc.emu_start(base+0x1F2970,0,count=1000)
                self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP),sp)
                values.append((uc.mem_read(t+0x400,1)[0],bytes(uc.mem_read(t+0x404,4))))
            self.assertEqual(values[0],values[1]);seen.add(values[0][0])
        self.assertEqual(seen,set(range(5)))
        self.assertTrue(all(0x300000000<=a<a+n<=sp+0x20 or t+0x400<=a<a+n<=t+0x408 for a,n in writes))

    def wheel_clamp(self,gear=0,*,enabled=True,condition=None,reverse=False,low_final=-1.):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
        uc=Uc(UC_ARCH_X86,UC_MODE_64)
        for address,size in ((api.base,0x3000000),(mode.allocation,m.ALLOCATION_SIZE),
                             (0x200000000,0x100000),(0x300000000,0x10000)):uc.mem_map(address,size)
        for address,value in api.memory.items():uc.mem_write(address,bytes([value]))
        pfx=e['pfx'];t=e['transmission'];header=mode.allocation+m.CODE_SIZE;engine=0x200074000
        wheels,distribution=0x200080000,0x20007A000;sp=0x300008000
        def put(a,data):uc.mem_write(a,data)
        def q(a,v):put(a,struct.pack('<Q',v))
        def f(a,v):put(a,struct.pack('<f',v))
        def u32(a,v):put(a,struct.pack('<I',v))
        put(api.base+0x23EE4E,NATIVE_WHEEL_CLAMP)
        put(mode.sites[2],mode._patches(mode.allocation)[2])
        put(api.base+0x237D10,m.SIGNATURES[0x237D10]);put(api.base+0x1F2920,NATIVE_RATIO)
        for rva,data in NATIVE_CONSTANTS.items():put(api.base+rva,data)
        put(api.base+0x23C7D0,NATIVE_GETTERS[0x23C7D0])
        q(api.base+m.PFX_VTABLE_RVA+0x370,api.base+0x237D10)
        q(api.base+m.PFX_VTABLE_RVA+0x368,api.base+0x23C7D0)
        q(pfx+0x1ED0,engine);f(engine+0x48,6850.);f(engine+0x24,50.)
        q(pfx+0x12B8,wheels);u32(pfx+0x12D0,4)
        q(t+0x70,distribution);put(distribution,struct.pack('<4f',*([.25]*4)))
        put(pfx+0x1EEC,bytes([reverse,gear]));f(t+0x3C,low_final)
        put(t+0x84,bytes([low_final>0]))
        radians_to_rpm=struct.unpack('<f',NATIVE_CONSTANTS[0x1974020][:4])[0]
        for index in range(4):f(wheels+index*0x1F0+0x150,20000./radians_to_rpm)
        protected=(bytes(uc.mem_read(t,0x80)),bytes(uc.mem_read(engine,0x64)))
        qpc=api.base+0x1000;put(qpc,b'\xc3');q(api.base+m.QPC_IAT_RVA,qpc)
        if not enabled:q(header+72,0)
        if condition=='expired':q(header+72,1000)
        if condition=='odd':q(header+64,3)
        if condition=='driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
        if condition=='world_loading':u32(e['world']+0x48,1)
        if condition=='transmission_changed':q(header+384,t+0x1000)
        calls=[];qpcs=[];writes=[]
        def trace(machine,address,size,_):
            if address==api.base+0x23EEDE:machine.emu_stop();return
            if address==api.base+0x237D10:
                self.assertEqual(machine.reg_read(x.UC_X86_REG_RSP)%16,8)
                self.assertEqual(machine.reg_read(x.UC_X86_REG_RDI),0xABC000)
                self.assertEqual(machine.reg_read(x.UC_X86_REG_RCX),pfx)
                calls.append(address)
            if address!=qpc:return
            qpcs.append(address);late=len(qpcs)==2
            q(machine.reg_read(x.UC_X86_REG_RCX),1300 if late and condition=='late_expiry' else 1000)
            if late and condition=='late_driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
            if late and condition=='late_sequence':q(header+64,8)
            for name in ('RAX','RCX','RDX','R8','R9','R10','R11'):
                machine.reg_write(getattr(x,'UC_X86_REG_'+name),0xBAD000)
            for index in range(6):machine.reg_write(getattr(x,'UC_X86_REG_XMM'+str(index)),0xBAD000)
            machine.reg_write(x.UC_X86_REG_RAX,0 if condition=='qpc_fail' else 1)
        uc.hook_add(UC_HOOK_CODE,trace)
        uc.hook_add(UC_HOOK_MEM_WRITE,lambda machine,access,a,n,v,_:writes.append((machine.reg_read(x.UC_X86_REG_RIP),a,n)))
        for register,value in ((x.UC_X86_REG_RBX,pfx),(x.UC_X86_REG_R14,0),(x.UC_X86_REG_RDI,0xABC000),
                               (x.UC_X86_REG_RSP,sp)):uc.reg_write(register,value)
        for register,value in ((x.UC_X86_REG_XMM8,0.),(x.UC_X86_REG_XMM9,20000.)):
            uc.reg_write(register,int.from_bytes(struct.pack('<f',value),'little'))
        uc.reg_write(x.UC_X86_REG_XMM10,0x80000000)
        uc.emu_start(api.base+0x23EE4E,0,count=20000)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_RIP),api.base+0x23EEDE)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP),sp);self.assertEqual(len(calls),1)
        self.assertEqual((bytes(uc.mem_read(t,0x80)),bytes(uc.mem_read(engine,0x64))),protected)
        self.assertTrue(all(0x300000000<=a<a+n<=sp or header+256<=a<a+n<=header+312
                            or header+416<=a<a+n<=header+448
                            or api.base+0x23EE80<=pc<api.base+0x23EEDE
                            and a in [wheels+j*0x1F0+0x150 for j in range(4)] for pc,a,n in writes),writes)
        wheel_rpms=[struct.unpack('<f',uc.mem_read(wheels+j*0x1F0+0x150,4))[0]*radians_to_rpm for j in range(4)]
        for value in wheel_rpms:self.assertAlmostEqual(value,wheel_rpms[0],places=4)
        api.put(header,bytes(uc.mem_read(header,m.HEADER_SIZE)))
        return mode.read_stats(),wheel_rpms[0]

    def test_native_wheel_clamp_exposes_old_first_gear_ceiling_and_full_shift_helper_advances_all_five_gears(self):
        for gear in range(5):
            with self.subTest(gear=gear):
                _,old=self.wheel_clamp(gear,enabled=False)
                stats,fixed=self.wheel_clamp(gear)
                self.assertAlmostEqual(fixed,old*2,places=3)
                self.assertEqual(stats['wheel_limit_scaled'],1)
                self.assertAlmostEqual(stats['effective_wheel_rpm'],stats['original_wheel_rpm']*2,places=4)
                _,failed=self.transmission(gear=gear,wheel_rpm=old,full_native=True)
                _,corrected=self.transmission(gear=gear,wheel_rpm=fixed,full_native=True)
                self.assertLessEqual(failed[0][3],gear)
                self.assertEqual(corrected[0][3],min(gear+1,4))
                if gear==0:
                    self.assertEqual(failed[0][3],0)
                    self.assertAlmostEqual(failed[0][1],3450.,places=2)

    def test_wheel_rpm_limit_owner_lease_transitions_reverse_and_low_range(self):
        for condition in ('expired','odd','driver_changed','world_loading','transmission_changed',
                          'qpc_fail','late_expiry','late_driver_changed','late_sequence'):
            with self.subTest(condition=condition):
                stats,rpm=self.wheel_clamp(condition=condition)
                self.assertEqual(stats['wheel_limit_scaled'],0)
                self.assertAlmostEqual(rpm,6900./(8.014*2.231),places=3)
        for reverse in (False,True):
            for low_final in (-1.,4.):
                _,old=self.wheel_clamp(enabled=False,reverse=reverse,low_final=low_final)
                _,fixed=self.wheel_clamp(reverse=reverse,low_final=low_final)
                self.assertAlmostEqual(fixed,old*2,places=3)

    def test_partial_six_site_or_previous_two_three_five_site_patch_is_refused_without_writes(self):
        for missing in range(len(m.ORIGINALS)):
            api=FakeAPI();game,_,_=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
            api.put(mode.sites[missing],m.ORIGINALS[missing]);api.events.clear()
            with self.assertRaises(RuntimeError):m.MadMaxSpeedMode(game,1,api=api).install()
            self.assertFalse(api.events)
        for old_count in (2,3,5):
            api=FakeAPI();game,_,_=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
            for site,original in zip(mode.sites[old_count:],m.ORIGINALS[old_count:]):api.put(site,original)
            api.events.clear()
            with self.assertRaisesRegex(RuntimeError,'Partial Mad Max patch'):m.MadMaxSpeedMode(game,1,api=api).install()
            self.assertFalse(api.events)

    def test_legacy_engine_output_hook_and_modified_native_continuation_refuse(self):
        for rva in (0x256954,m.NATIVE_PREFIX_RVA,m.NATIVE_CONTINUATION_RVA):
            api=FakeAPI();game,_,_=fixture(api);api.put(api.base+rva,b'\x90')
            with self.assertRaises(RuntimeError):m.MadMaxSpeedMode(game,1,api=api).publish()
            self.assertFalse(api.events)

    def grip(self,axis,*,enabled=True,angle=10.,slip=.2,load=1000.,demand=10000.,wheel=0,
             condition=None,raw_limit=None,material=1.):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
        uc=Uc(UC_ARCH_X86,UC_MODE_64)
        for address,size in ((api.base,0x3000000),(mode.allocation,m.ALLOCATION_SIZE),
                             (0x200000000,0x100000),(0x300000000,0x10000)):uc.mem_map(address,size)
        for address,value in api.memory.items():uc.mem_write(address,bytes([value]))
        def put(a,data):uc.mem_write(a,data)
        def q(a,v):put(a,struct.pack('<Q',v))
        def u32(a,v):put(a,struct.pack('<I',v))
        def f(a,v):put(a,struct.pack('<f',v))
        def regf(register,value):uc.reg_write(register,int.from_bytes(struct.pack('<f',value),'little'))
        pfx=e['pfx'];header=mode.allocation+m.CODE_SIZE;profile=0x2000A0000
        wheels=0x200080000;w=wheels+wheel*0x1F0;sp=0x300008000
        for rva,data in NATIVE_GRIP.items():put(api.base+rva,data)
        for rva,data in NATIVE_GRIP_CONSTANTS.items():put(api.base+rva,data)
        for site,patch in zip(mode.sites,mode._patches(mode.allocation)):put(site,patch)
        # Original linear evaluator with asymmetric combined-slip curve samples.
        for j,offset in enumerate((0,0x90,0x120,0x1B0,0x240,0x2D0,0x368,0x3F8,0x488,0x518,0x5A8)):
            limit=1. if offset<0x368 else 45.
            put(profile+offset,struct.pack('<4f',0.,limit,0.,1.))
            put(profile+offset+0x10,struct.pack('<3f',0.,.2,1.))
            put(profile+offset+0x38,struct.pack('<3f',0.,1.-j*.025,.5-j*.02))
            u32(profile+offset+0x88,0);u32(profile+offset+0x8C,3)
        for offset,value in ((0x360,10.),(0x364,30.),(0x638,.1),(0x63C,.5),(0x640,-.1),(0x644,-.5)):
            f(profile+offset,value)
        q(pfx+0x12B8,wheels);u32(pfx+0x12D0,4);u32(pfx+0x12D4,2)
        for j in range(4):
            u32(wheels+j*0x1F0+0x20,0x100+j)
            f(wheels+j*0x1F0+0x188,1.5);f(wheels+j*0x1F0+0x190,1.)
        f(sp+0x30,material);f(sp+0x40,1.);q(sp+0x38,0x2000C0000)
        if not enabled:q(header+72,0)
        if condition=='expired':q(header+72,1000)
        if condition=='odd':q(header+64,3)
        if condition=='driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
        if condition=='dismounted':u32(e['vehicle_source']+0x54,0)
        if condition=='world_loading':u32(e['world']+0x48,1)
        if condition=='transmission_changed':q(header+384,e['transmission']+0x1000)
        if condition in ('air','invalid_contact'):u32(w+0x20,0x7FFFFFFF)
        if condition=='reverse':put(pfx+0x1EE0,b'\1');put(pfx+0x1EEC,b'\1')
        if condition=='unaligned_wheel':w+=4
        if condition=='bad_factor':f(w+0x188,float('nan'))
        before=(bytes(uc.mem_read(profile,0x660)),bytes(uc.mem_read(pfx,0x2200)),
                bytes(uc.mem_read(e['transmission'],0x180)))
        qpc=api.base+0x1000;put(qpc,b'\xc3');q(api.base+m.QPC_IAT_RVA,qpc)
        site=mode.sites[3+axis];continuation=site+8
        native=api.base+(0x2377E0 if axis==0 else 0x2372E0)
        stop=api.base+(0x2259F2 if axis==0 else 0x225D08)
        calls=[];qpcs=[];snapshots=[];writes=[];curve_inputs=[]
        def snapshot():
            names=('RAX','RCX','RDX','R8','R9','R10','R11','RBX','RBP','RSI','RDI','R12','R13','R14','R15')
            return ([uc.reg_read(getattr(x,'UC_X86_REG_'+n)) for n in names],
                    [uc.reg_read(getattr(x,'UC_X86_REG_XMM'+str(j))) for j in range(16)],uc.reg_read(x.UC_X86_REG_EFLAGS))
        def trace(machine,address,size,_):
            if address in (stop,api.base+0x225FF9):machine.emu_stop();return
            if address==native:
                calls.append(address);curve_inputs.append(tuple(machine.reg_read(r)&0xFFFFFFFF for r in
                    (x.UC_X86_REG_XMM1,x.UC_X86_REG_XMM2,x.UC_X86_REG_XMM3)))
            if address==continuation:snapshots.append(snapshot())
            # Supply demanded tire force separately; execute the original clamp.
            if address==api.base+(0x22598E if axis==0 else 0x225B3B):
                regf(x.UC_X86_REG_XMM4 if axis==0 else x.UC_X86_REG_XMM6,demand)
                machine.reg_write(x.UC_X86_REG_RIP,api.base+(0x2259E2 if axis==0 else 0x225CF8));return
            if address!=qpc:return
            qpcs.append(address);late=len(qpcs)==2
            q(machine.reg_read(x.UC_X86_REG_RCX),1300 if late and condition=='late_expiry' else 1000)
            if late and condition=='late_driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
            if late and condition=='late_sequence':q(header+64,8)
            for name in ('RAX','RCX','RDX','R8','R9','R10','R11'):
                machine.reg_write(getattr(x,'UC_X86_REG_'+name),0xBAD000)
            for j in range(6):machine.reg_write(getattr(x,'UC_X86_REG_XMM'+str(j)),0xBAD000)
            machine.reg_write(x.UC_X86_REG_RAX,0 if condition=='qpc_fail' else 1)
        uc.hook_add(UC_HOOK_CODE,trace)
        uc.hook_add(UC_HOOK_MEM_WRITE,lambda machine,access,a,n,v,_:writes.append((machine.reg_read(x.UC_X86_REG_RIP),a,n)))
        for register,value in ((x.UC_X86_REG_RSI,pfx),(x.UC_X86_REG_RBX,w),(x.UC_X86_REG_RDI,profile),
                               (x.UC_X86_REG_RCX,profile),(x.UC_X86_REG_R13,wheel)):
            uc.reg_write(register,value)
        regf(x.UC_X86_REG_XMM1,load);regf(x.UC_X86_REG_XMM2,angle);regf(x.UC_X86_REG_XMM3,slip)
        regf(x.UC_X86_REG_XMM7,load);regf(x.UC_X86_REG_XMM8,0.);regf(x.UC_X86_REG_XMM14,1.)
        regf(x.UC_X86_REG_XMM11,1./60.)
        if condition=='air':
            start=api.base+0x2253F0;uc.reg_write(x.UC_X86_REG_RSP,sp)
        elif raw_limit is not None:
            start=site;uc.reg_write(x.UC_X86_REG_RSP,sp)
            regf(x.UC_X86_REG_XMM0 if axis==0 else x.UC_X86_REG_XMM7,raw_limit)
        else:
            start=native;uc.reg_write(x.UC_X86_REG_RSP,sp-8)
            q(sp-8,site if axis==0 else api.base+0x225AE1)
        uc.emu_start(start,0,count=30000)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP),sp)
        self.assertIn(uc.reg_read(x.UC_X86_REG_RIP),(stop,api.base+0x225FF9))
        self.assertEqual(len(calls),0 if raw_limit is not None or condition=='air' else 1)
        if curve_inputs:self.assertEqual(curve_inputs[0],tuple(int.from_bytes(struct.pack('<f',v),'little') for v in (load,angle,slip)))
        self.assertEqual((bytes(uc.mem_read(profile,0x660)),bytes(uc.mem_read(pfx,0x2200)),
                          bytes(uc.mem_read(e['transmission'],0x180))),before)
        self.assertTrue(all(0x300000000<=a<a+n<=sp+0x80 or header+256<=a<a+n<=header+312
                            or header+448<=a<a+n<=header+496
                            or api.base+0x2253F0<=pc<api.base+0x225422 and a in (w+0x150,w+0x19C) for pc,a,n in writes),writes)
        value=uc.reg_read(x.UC_X86_REG_XMM4 if axis==0 else x.UC_X86_REG_XMM6)&0xFFFFFFFF
        result=struct.unpack('<f',struct.pack('<I',value))[0]
        api.put(header,bytes(uc.mem_read(header,m.HEADER_SIZE)))
        return mode.read_stats(),result,snapshots

    def test_original_combined_slip_curves_keep_inputs_shape_and_native_demand_clamps(self):
        for axis in (0,1):
            for angle in (-20.,-5.,0.,5.,20.):
                for slip in (-.3,0.,.3):
                    with self.subTest(axis=axis,angle=angle,slip=slip):
                        _,old,off=self.grip(axis,enabled=False,angle=angle,slip=slip)
                        stats,new,on=self.grip(axis,angle=angle,slip=slip)
                        self.assertAlmostEqual(new,old*2,places=3)
                        self.assertEqual(stats['grip_scaled'],1)
                        expected=[list(off[0][0]),list(off[0][1]),off[0][2]]
                        target=0 if axis==0 else 7
                        original=expected[1][target]&0xFFFFFFFF
                        scaled=struct.unpack('<f',struct.pack('<I',original))[0]*2
                        expected[1][target]=(expected[1][target]&~0xFFFFFFFF)|int.from_bytes(struct.pack('<f',scaled),'little')
                        self.assertEqual(on[0],tuple(expected))
            for demand in (-1.,0.,1.):
                # The native clamp receives demand and the signed curve ceiling
                # in the same direction; zero demand has zero corresponding slip.
                angle=(10. if demand>0 else -10. if demand<0 else 0.) if axis else 10.
                slip=(.3 if demand>0 else -.3 if demand<0 else 0.) if not axis else .3
                _,old,_=self.grip(axis,enabled=False,angle=angle,slip=slip,demand=demand)
                _,new,_=self.grip(axis,angle=angle,slip=slip,demand=demand)
                self.assertEqual(new,old)

    def test_grip_all_wheels_contact_owner_lease_and_off_boundaries(self):
        for axis in (0,1):
            for wheel in range(4):
                stats,_,_=self.grip(axis,wheel=wheel)
                self.assertEqual(stats['grip_scaled'],1);self.assertEqual(stats['grip_axis'],axis+1)
                self.assertEqual(stats['grip_wheel'],0x200080000+wheel*0x1F0)
            stats,_,_=self.grip(axis,condition='air');self.assertEqual(stats['grip_calls'],0)
            stats,_,_=self.grip(axis,condition='reverse');self.assertEqual(stats['grip_scaled'],1)
            for load in (0.,1000.):
                stats,value,_=self.grip(axis,angle=0.,slip=0.,load=load,demand=0.)
                self.assertEqual(value,0.)
            for condition in ('expired','odd','driver_changed','dismounted','world_loading','transmission_changed','invalid_contact',
                              'unaligned_wheel','bad_factor','qpc_fail','late_expiry','late_driver_changed','late_sequence'):
                with self.subTest(axis=axis,condition=condition):
                    stats,_,_=self.grip(axis,condition=condition);self.assertEqual(stats['grip_scaled'],0)

    def test_grip_zero_nonfinite_overflow_signed_limits_and_material_factors_preserve_native_demand(self):
        for axis in (0,1):
            for value in (-0.,0.,float('inf'),float('-inf'),float('nan'),2**127,-2**127):
                with self.subTest(axis=axis,value=value):
                    _,old,_=self.grip(axis,enabled=False,raw_limit=value)
                    stats,new,_=self.grip(axis,raw_limit=value)
                    if math.isnan(old):self.assertTrue(math.isnan(new))
                    else:self.assertEqual(new,old)
                    self.assertEqual(stats['grip_scaled'],1 if value==0 else 0)
            for material in (0.,.2,1.):
                _,old,_=self.grip(axis,enabled=False,material=material)
                _,new,_=self.grip(axis,material=material)
                self.assertAlmostEqual(new,old*2,places=3)


    def aero(self,kph,*,enabled=True,coefficient=2.3897194862365723,condition=None,lift=True):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api=FakeAPI();game,b,e=fixture(api);mode=m.MadMaxSpeedMode(game,1,api=api);mode.publish()
        uc=Uc(UC_ARCH_X86,UC_MODE_64)
        for address,size in ((api.base,0x3000000),(mode.allocation,m.ALLOCATION_SIZE),
                             (0x200000000,0x100000),(0x300000000,0x10000)):uc.mem_map(address,size)
        for address,value in api.memory.items():uc.mem_write(address,bytes([value]))
        def put(a,data):uc.mem_write(a,data)
        def q(a,v):put(a,struct.pack('<Q',v))
        def u32(a,v):put(a,struct.pack('<I',v))
        def f(a,*v):put(a,struct.pack('<'+'f'*len(v),*v))
        pfx=e['pfx'];header=mode.allocation+m.CODE_SIZE;profile=0x200080000
        body,motion,output=0x200090000,0x2000A0000,0x2000B0000
        sp,stop=0x300008008,api.base+0x1200
        put(api.base+0x223F20,NATIVE_AERO)
        for rva,data in NATIVE_AERO_CONSTANTS.items():put(api.base+rva,data)
        for site,patch in zip(mode.sites,mode._patches(mode.allocation)):put(site,patch)
        q(pfx+0x4D0,profile);q(pfx+0x4E0,0);f(pfx+0x4BC,120./3.6)
        f(profile,1.2999999523162842,1.2464491128921509,coefficient,5.974298477172852,-.10000000149011612)
        put(profile+0x100,bytes(uc.mem_read(profile,20)))
        f(body,1.,0.,0.,0.);f(body+16,0.,1.,0.,0.);f(body+32,0.,0.,1.,0.)
        f(motion+0x40,0.,0.,kph/3.6,0.)
        q(api.base+m.PFX_VTABLE_RVA+0x240,api.base+0x1100)
        put(api.base+0x1100,b'\xb0'+bytes([int(lift)])+b'\xc3')
        qpc=api.base+0x1000;put(qpc,b'\xc3');q(api.base+m.QPC_IAT_RVA,qpc)
        if not enabled:q(header+72,0)
        if condition=='expired':q(header+72,1000)
        if condition=='odd':q(header+64,3)
        if condition=='driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
        if condition=='dismounted':u32(e['vehicle_source']+0x54,0)
        if condition=='world_loading':u32(e['world']+0x48,1)
        if condition=='transmission_changed':q(header+384,e['transmission']+0x1000)
        if condition=='air':q(pfx+0x12B8,0);u32(pfx+0x12D0,0)
        before=(bytes(uc.mem_read(profile,0x120)),bytes(uc.mem_read(pfx,0x2200)),
                bytes(uc.mem_read(e['transmission'],0x180)))
        snapshots=[];qpcs=[];calls=[];writes=[]
        def snapshot():
            names=('RAX','RCX','RDX','R8','R9','R10','R11','RBX','RBP','RSI','RDI','R12','R13','R14','R15')
            return ([uc.reg_read(getattr(x,'UC_X86_REG_'+n)) for n in names],
                    [uc.reg_read(getattr(x,'UC_X86_REG_XMM'+str(j))) for j in range(16)],uc.reg_read(x.UC_X86_REG_EFLAGS))
        def trace(machine,address,size,_):
            if address==api.base+0x223F20:calls.append(address)
            if address==api.base+m.AERO_SITE_RVA and condition=='foreign_profile':
                machine.reg_write(x.UC_X86_REG_RCX,profile+0x100)
            if address==api.base+m.AERO_SITE_RVA+5:snapshots.append(snapshot())
            if address!=qpc:return
            qpcs.append(address);late=len(qpcs)==2
            q(machine.reg_read(x.UC_X86_REG_RCX),1300 if late and condition=='late_expiry' else 1000)
            if late and condition=='late_driver_changed':u32(e['vehicle_source']+0x54,b['handle']+1)
            if late and condition=='late_sequence':q(header+64,8)
            for name in ('RAX','RCX','RDX','R8','R9','R10','R11'):machine.reg_write(getattr(x,'UC_X86_REG_'+name),0xBAD000)
            for j in range(6):machine.reg_write(getattr(x,'UC_X86_REG_XMM'+str(j)),0xBAD000)
            machine.reg_write(x.UC_X86_REG_RAX,0 if condition=='qpc_fail' else 1)
        uc.hook_add(UC_HOOK_CODE,trace)
        uc.hook_add(UC_HOOK_MEM_WRITE,lambda machine,access,a,n,v,_:writes.append((a,n)))
        for register,value in ((x.UC_X86_REG_RCX,pfx),(x.UC_X86_REG_RDX,body),
                               (x.UC_X86_REG_R8,motion),(x.UC_X86_REG_R9,output),(x.UC_X86_REG_RSP,sp)):
            uc.reg_write(register,value)
        q(sp,stop);writes.clear()
        uc.emu_start(api.base+0x223F20,stop,count=20000)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_RIP),stop)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP),sp+8)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(snapshots),1)
        self.assertEqual((bytes(uc.mem_read(profile,0x120)),bytes(uc.mem_read(pfx,0x2200)),
                          bytes(uc.mem_read(e['transmission'],0x180))),before)
        # The original native prologue saves RBX/RSI in the caller's home area.
        self.assertFalse([(a,n) for a,n in writes if not
                          (sp-0x1000<=a<a+n<=sp+0x28 or output<=a<a+n<=output+32
                           or header+256<=a<a+n<=header+312 or header+512<=a<a+n<=header+544)])
        api.put(header,bytes(uc.mem_read(header,m.HEADER_SIZE)))
        mode._verify_owned(mode.allocation)
        return mode.read_stats(),struct.unpack('<4f',uc.mem_read(output,16)),snapshots[0]

    def test_original_aerodynamics_base_half_matches_double_speed_double_drag_and_keeps_high_drag_and_lift(self):
        _,stock,_=self.aero(38.90467,enabled=False)
        _,old,_=self.aero(77.80934,enabled=False)
        stats,new,_=self.aero(77.80934)
        self.assertAlmostEqual(old[2],4*stock[2],places=3)
        self.assertAlmostEqual(new[2],2*stock[2],places=3)
        self.assertEqual(new[1],old[1])
        self.assertEqual(stats['aero_scaled'],1)
        self.assertAlmostEqual(stats['effective_aero_coefficient'],stats['original_aero_coefficient']*.5)
        for kph in (-77.80934,0.,120.,123.6,127.2,140.):
            _,old,_=self.aero(kph,enabled=False);_,new,_=self.aero(kph)
            self.assertEqual(new[1],old[1])
            if abs(kph)<=120:self.assertAlmostEqual(new[2],old[2]*.5,places=3)
            elif kph>=127.2:self.assertEqual(new[2],old[2])
            else:self.assertLess(abs(new[2]),abs(old[2]))
        _,without_lift,_=self.aero(77.80934,lift=False)
        _,with_lift,_=self.aero(77.80934)
        self.assertEqual(without_lift[1],0.)
        self.assertEqual(without_lift[2],with_lift[2])

    def test_aero_owner_lease_off_air_profile_scope_and_full_abi_boundaries(self):
        _,_,off=self.aero(80.,enabled=False);_,_,on=self.aero(80.)
        expected=[list(off[0]),list(off[1]),off[2]]
        expected[1][1]=int.from_bytes(struct.pack('<f',2.3897194862365723*.5),'little')
        self.assertEqual(on,tuple(expected))
        stats,_,_=self.aero(80.,condition='air');self.assertEqual(stats['aero_scaled'],1)
        for condition in ('expired','odd','driver_changed','dismounted','world_loading','transmission_changed',
                          'foreign_profile','qpc_fail','late_expiry','late_driver_changed','late_sequence'):
            with self.subTest(condition=condition):
                _,old,off=self.aero(80.,enabled=False,condition=condition)
                stats,new,on=self.aero(80.,condition=condition)
                self.assertEqual(stats['aero_scaled'],0);self.assertEqual(new,old);self.assertEqual(on,off)

    def test_aero_zero_negative_nonfinite_and_underflow_preserve_original_load(self):
        for value in (-0.,0.,-1.,float('inf'),float('-inf'),float('nan'),2**-126,2**-149):
            with self.subTest(coefficient=value):
                _,_,off=self.aero(80.,enabled=False,coefficient=value)
                stats,_,on=self.aero(80.,coefficient=value)
                self.assertEqual(stats['aero_scaled'],0);self.assertEqual(on,off)


if __name__=='__main__':unittest.main()
