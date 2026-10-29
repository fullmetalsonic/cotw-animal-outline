"""Small UI catalog selected by the Windows display language, once per launch."""
import ctypes
import re
from string import Formatter


def language_from_langid(langid):
    if isinstance(langid, int) and not isinstance(langid, bool) and 0 < langid <= 0xFFFF:
        return 'ko' if langid & 0x3FF == 0x12 else 'en'
    return 'en'


def detect_language(get_ui_language=None):
    try:
        if get_ui_language is None:
            get_ui_language = ctypes.windll.kernel32.GetUserDefaultUILanguage
            get_ui_language.argtypes = []
            get_ui_language.restype = ctypes.c_ushort
        return language_from_langid(get_ui_language())
    except Exception:
        return 'en'


LANGUAGE = detect_language()

EN = {
    'AI 입력 목록이 유효하지 않습니다': 'The AI input list is invalid',
    'COTW 게임 모드': 'COTW Game Modes',
    'COTW 사냥감 윤곽 ON/OFF': 'COTW animal outline ON/OFF',
    'COTW 사냥감 윤곽 모드': 'COTW Animal Outline',
    'GUI의 초기 색상 선택': 'Initial outline color in the GUI',
    '검증되지 않은 사냥감은 갱신하지 않습니다': 'Unverified animals are excluded from updates',
    '게임 AI 입력 관리자를 확인하지 못했습니다': 'Could not identify the game AI input manager',
    '게임 AI 입력 목록을 확인하지 못했습니다': 'Could not read the game AI input list',
    '게임 AI 입력 목록이 유효하지 않습니다': 'The game AI input list is invalid',
    '게임 모드 메모리 기록 검증에 실패했습니다': 'Game mode memory write verification failed',
    '게임 모드 메모리 보호 변경에 실패했습니다': 'Could not change game mode memory protection',
    '게임 모드 메모리 쓰기에 실패했습니다': 'Could not write game mode memory',
    '게임 모드 명령 캐시 갱신에 실패했습니다': 'Could not flush the game mode instruction cache',
    '게임 모드 쓰기 범위가 잘못되었습니다': 'The game mode write range is invalid',
    '게임 모드이 호출 범위를 벗어났습니다': 'The game mode call target is out of range',
    '게임 스레드 목록을 끝까지 확인하지 못했습니다': 'Could not finish enumerating game threads',
    '게임 스레드 목록을 확인하지 못했습니다': 'Could not enumerate game threads',
    '게임 스레드 목록이 안정적이지 않습니다': 'The game thread list is changing',
    '게임 스레드 소속이 바뀌었습니다': 'A game thread changed ownership',
    '게임 스레드 실행 위치를 확인하지 못했습니다': 'Could not read a game thread instruction pointer',
    '게임 스레드가 변경 위치를 실행 중이어서 설치하지 않았습니다': 'Installation paused because a game thread is executing the patch site',
    '게임 스레드를 안전하게 중단하지 못했습니다': 'Could not safely suspend game threads',
    '게임 스레드를 일시 중단하지 못했습니다': 'Could not suspend a game thread',
    '게임 실행 코드가 검증 버전과 달라 모드를 껐습니다': 'Mode disabled: the running game code differs from the verified build',
    '게임 연결 대기 · 모드 OFF': 'Waiting for game · Mode OFF',
    '게임 연결 확인 중 · 모드 OFF': 'Checking game connection · Mode OFF',
    '게임 파일이 변경되어 모드를 껐습니다': 'Mode disabled: the game executable changed',
    '게임 프로세스 접근 권한을 얻지 못했습니다. 게임과 모드의 실행 권한을 확인하세요.': 'Could not access the game process. Check the permissions of the game and this app.',
    '게임이 종료되어 모드를 껐습니다': 'Mode disabled: the game exited',
    '기존 닌자 모드 소유권과 코드를 확인하지 못했습니다': 'Could not verify the existing Ninja mode ownership and code',
    '기존 닌자 모드 위치가 유효하지 않습니다': 'The existing Ninja mode allocation is invalid',
    '기존 반려견 윤곽 모드 소유권을 확인하지 못했습니다': 'Could not verify the existing dog outline ownership',
    '기존 반려견 윤곽 모드 위치가 유효하지 않습니다': 'The existing dog outline allocation is invalid',
    '기존 사체 훅 소유권과 코드를 확인하지 못했습니다': 'Could not verify the existing carcass hook ownership and code',
    '기존 사체 훅 위치가 유효하지 않습니다': 'The existing carcass hook allocation is invalid',
    '기존 헬하운드 모드 소유권을 확인하지 못했습니다': 'Could not verify the existing Hellhound mode ownership',
    '기존 헬하운드 모드 위치가 유효하지 않습니다': 'The existing Hellhound mode allocation is invalid',
    '닌자 OFF': 'Ninja OFF',
    '닌자 ON': 'Ninja ON',
    '닌자 ON · 상태 전환 대기': 'Ninja ON · Waiting for transition',
    '닌자 모드 · 독립 ON/OFF': 'Ninja mode · Independent ON/OFF',
    '닌자 모드 감지 코드가 검증된 버전과 다릅니다': 'The Ninja detection code differs from the verified build',
    '닌자 모드 바이너리를 확인하지 못했습니다': 'Could not verify the Ninja mode binary',
    '닌자 모드 설치 실패: 원본 호출 코드를 복원했습니다': 'Ninja installation failed; original calls restored',
    '닌자 모드 설치와 원본 복원에 실패했습니다. 게임을 종료하세요': 'Ninja installation and restoration failed. Close the game.',
    '닌자 모드 호출 코드 기록 검증 실패': 'Ninja call patch verification failed',
    '닌자 모드 호출 코드가 다른 프로그램에 의해 변경되었습니다': 'Another program modified the Ninja call site',
    '닌자 모드 호출 코드가 바뀌었습니다': 'The Ninja call site changed',
    '닌자 모드를 위한 게임 프로세스 접근 권한을 얻지 못했습니다': 'Could not access the game process for Ninja mode',
    '단축키 등록 실패 · 전체 ON/OFF 버튼을 사용하세요.': 'Hotkey unavailable · Use the All ON/OFF buttons.',
    '대상 빌드: 26051119 · 싱글플레이 전용': 'Target build: 26051119 · Single-player only',
    '로컬 플레이어 연결이 변경 중입니다': 'The local player binding is changing',
    '리트리버 연결이 변경 중입니다': 'The retriever binding is changing',
    '리트리버 작업 연결을 기다리고 있습니다': 'Waiting for a retriever task binding',
    '리트리버가 1~9등급 사체를 회수합니다. 1급은 기존 동작, 2~9급은 개의 입을 따라 지면에 끌려옵니다. 운반 중에는 장애물을 통과하고, 도착·취소·OFF 때 내려놓습니다. E로 수확할 수 있으며 실제 등급·무게는 바꾸지 않습니다. 리트리버 DLC와 활성 반려견이 필요합니다.': 'Lets the retriever fetch class 1–9 carcasses. Class 1 keeps native behavior; classes 2–9 follow the dog\'s mouth and drag along the ground. Carried carcasses pass through obstacles and are released on arrival, cancellation or OFF. Harvest with E; actual class and weight remain unchanged. Requires the retriever DLC and an active dog.',
    '맑은 고딕': 'Malgun Gothic',
    '모드 OFF': 'Mode OFF',
    '모드 OFF · 종료 중': 'Mode OFF · Closing',
    '모드 ON': 'Mode ON',
    '모든 무기의 발사음은 롱보우, 탄착음은 활 소리로 바꾸고 총기 발사 반향은 차단합니다. 사냥감의 발사·탄착 소음 계산도 롱보우 기준으로 적용합니다. 탄도·피해·탄약과 장전 소리는 유지합니다. OFF에서는 원래 소리와 계산으로 돌아갑니다.': 'Uses longbow firing sounds and bow impact sounds for all weapons, and suppresses gunshot tails. Animal hearing calculations for shots and impacts also use the longbow profile. Ballistics, damage, ammunition, and reload sounds stay unchanged. OFF restores native sounds and calculations.',
    '반려견 AI 입력 세대가 변경 중입니다': 'The dog AI input generation is changing',
    '반려견 AI 입력이 변경 중입니다': 'The dog AI input is changing',
    '반려견 목록이 변경 중입니다': 'The dog list is changing',
    '반려견 연결이 변경 중입니다': 'The dog binding is changing',
    '반려견 윤곽 OFF': 'Dog outline OFF',
    '반려견 윤곽 ON': 'Dog outline ON',
    '반려견 윤곽 ON · 연결 대기': 'Dog outline ON · Waiting for connection',
    '반려견 윤곽 모드 바이너리를 확인하지 못했습니다': 'Could not verify the dog outline binary',
    '반려견 윤곽 설치 실패: 원본 코드를 복원했습니다': 'Dog outline installation failed; original code restored',
    '반려견 윤곽 설치와 복원에 실패했습니다. 게임을 종료하세요': 'Dog outline installation and restoration failed. Close the game.',
    '반려견 윤곽 유지 · 독립 ON/OFF': 'Keep dog outline · Independent ON/OFF',
    '반려견 윤곽 코드 기록 검증 실패': 'Dog outline patch verification failed',
    '반려견 윤곽 코드가 검증된 버전과 다릅니다': 'The dog outline code differs from the verified build',
    '반려견 윤곽 코드가 다른 프로그램에 의해 변경되었습니다': 'Another program modified the dog outline code',
    '반려견 윤곽 호출 코드가 바뀌었습니다': 'The dog outline call site changed',
    '반려견 윤곽을 위한 게임 프로세스 접근 권한을 얻지 못했습니다': 'Could not access the game process for dog outlines',
    '반려견 주인 연결이 변경 중입니다': 'The dog owner binding is changing',
    '반려견 주인을 하나로 확인하지 못했습니다': 'Could not identify a unique dog owner',
    '배포 페이지 열기': 'Open release page',
    '사냥감 리소스 경로가 바뀌었습니다': 'The animal resource path changed',
    '사냥감 메모리를 더 이상 읽을 수 없습니다': 'The animal memory is no longer readable',
    '사냥감 목록 구조가 검증된 버전과 달라 읽기를 중단했습니다.': 'Stopped reading: the animal list layout differs from the verified build.',
    '사냥감 윤곽 모드가 이미 열려 있습니다.\n기존 창에서 ON/OFF를 조작하세요.': 'Animal Outline is already open.\nUse ON/OFF in the existing window.',
    '사냥감 캐릭터가 바뀌었습니다': 'The animal character changed',
    '사냥감 포인터가 바뀌어 이번 갱신에서 제외했습니다': 'Skipped this update because the animal pointer changed',
    '사냥감의 생존 상태가 바뀌어 다음 목록에서 확인합니다': 'The animal life state changed; it will be checked in the next scan',
    '사냥감이 해제되거나 렌더링 대상에서 빠졌습니다': 'The animal was released or removed from rendering',
    '사냥감이 해제되었습니다': 'The animal was released',
    '사냥개 관리자 연결을 기다리고 있습니다': 'Waiting for the hunting dog manager',
    '사냥터 연결이 바뀌어 모드를 껐습니다': 'Mode disabled: the reserve binding changed',
    '사냥터를 불러오는 중이거나 사냥터를 벗어나 모드를 껐습니다': 'Mode disabled: the reserve is loading or has been left',
    '사냥터를 불러온 뒤 모드를 켜세요.': 'Load a reserve, then enable the mode.',
    '사냥터에 들어간 뒤 닌자 모드를 켜세요': 'Enter a reserve before enabling Ninja mode',
    '사체 OFF': 'Carcasses OFF',
    '사체 OFF · 대상 0마리': 'Carcasses OFF · 0 targets',
    '사체 ON': 'Carcasses ON',
    '사체 모드 임시 유효시간을 확인하지 못했습니다': 'Could not read the carcass mode lease clock',
    '사체 목록이 검증된 크기를 초과했습니다': 'The carcass list exceeds the verified limit',
    '사체 색상: #FF5900 · 변경': 'Carcass color: #FF5900 · Change',
    '사체 색상은 0~1 범위의 RGB 값이어야 합니다': 'Carcass color must use RGB values from 0 to 1',
    '사체 색상은 0~1 범위의 RGB 세 값이어야 합니다': 'Carcass color must contain three RGB values from 0 to 1',
    '사체 윤곽 색상': 'Carcass outline color',
    '사체 윤곽 엔진 코드가 검증된 버전과 다릅니다': 'The carcass outline engine code differs from the verified build',
    '사체 표시 · 독립 ON/OFF': 'Carcass display · Independent ON/OFF',
    '사체 표시를 위한 게임 프로세스 접근 권한을 얻지 못했습니다': 'Could not access the game process for carcass display',
    '사체 호출 코드 기록 검증에 실패했습니다': 'Carcass call patch verification failed',
    '사체 호출 코드가 다른 프로그램에 의해 변경되었습니다': 'Another program modified the carcass call site',
    '사체 훅 바이너리를 확인하지 못했습니다': 'Could not verify the carcass hook binary',
    '사체 훅 설치 실패: 원본 호출 코드를 복원했습니다': 'Carcass hook installation failed; original calls restored',
    '사체 훅 설치와 원본 복원에 실패했습니다. 게임을 종료하세요': 'Carcass hook installation and restoration failed. Close the game.',
    '사체 훅 호출 코드가 바뀌었습니다': 'The carcass hook call site changed',
    '사체만 별도 색상으로 표시합니다. OFF에서는 게임의 기본 사체 표시로 돌아갑니다.': 'Shows carcasses in a separate color. OFF restores the native carcass display.',
    '살아 있는 사냥감: 0마리': 'Live animals: 0',
    '살아 있는 사냥감의 윤곽 갱신이 중지되었습니다.': 'Live animal outline updates are stopped.',
    '새 버전이 있습니다.': 'A new version is available.',
    '색상은 쓰기를 중지한 OFF 상태에서 변경하세요': 'Turn the mode OFF before changing its color',
    '설치 중 게임 스레드 목록이 바뀌었습니다': 'The game thread list changed during installation',
    '설치 중 닌자 모드 호출 코드가 바뀌었습니다': 'The Ninja call site changed during installation',
    '설치 중 반려견 윤곽 코드가 바뀌었습니다': 'The dog outline code changed during installation',
    '설치 중 사체 호출 코드가 바뀌었습니다': 'The carcass call site changed during installation',
    '설치 중 헬하운드 코드가 바뀌었습니다': 'The Hellhound code changed during installation',
    '소음기 OFF': 'Silencer OFF',
    '소음기 ON': 'Silencer ON',
    '소음기 ON · 롱보우': 'Silencer ON · Longbow',
    '소음기 ON · 연결 대기': 'Silencer ON · Waiting for connection',
    '소음기 모드 · 독립 ON/OFF': 'Silencer mode · Independent ON/OFF',
    '소음기 모드를 위한 게임 프로세스 접근 권한을 얻지 못했습니다': 'Could not access the game process for Silencer mode',
    '실행 중인 게임 모듈을 확인하지 못했습니다.': 'Could not identify the running game module.',
    '실행 중인 게임 파일 이름을 확인하지 못했습니다.': 'Could not identify the running game executable.',
    '쓰기 핸들이 닫혀 있습니다': 'The write handle is closed',
    '아직 정식 배포 정보를 확인할 수 없습니다.': 'Stable release information is not available yet.',
    '안전한 근거리 게임 모드 공간을 확보하지 못했습니다': 'Could not allocate safe memory near the game call site',
    '업데이트': 'Updates',
    '업데이트 확인': 'Check for updates',
    '업데이트가 필요하지 않습니다.': 'No update is needed.',
    '업데이트를 확인하지 못했습니다. 모드는 계속 사용할 수 있습니다.': 'Could not check for updates. You can keep using the modes.',
    '연결됨 · 모드 OFF': 'Connected · Mode OFF',
    '연결이 지연되어 확인하지 못했습니다. 모드는 계속 사용할 수 있습니다.': 'The update check timed out. You can keep using the modes.',
    '오류 · 모드 OFF': 'Error · Mode OFF',
    '원본 코드 복원 검증 실패': 'Original code restoration verification failed',
    '원본 호출 코드 복원 검증 실패': 'Original call restoration verification failed',
    '유한한 임시 윤곽 값만 허용합니다': 'Only finite temporary outline values are allowed',
    '윤곽 갱신을 중지했습니다. 임시 윤곽은 게임 진행 중 잠시 후 사라집니다.': 'Outline updates stopped. Temporary outlines will fade shortly during gameplay.',
    '윤곽 메모리 쓰기에 실패하여 모드를 중지했습니다': 'Mode stopped because an outline memory write failed',
    '윤곽 색상 (OFF에서 선택):': 'Outline color (select while OFF):',
    '윤곽 쓰기는 정확히 28바이트여야 합니다': 'An outline write must be exactly 28 bytes',
    '이 빌드의 사냥감 구분 검증이 아직 완료되지 않았습니다': 'Animal classification has not been verified for this build',
    '이동·탈것 소음과 플레이어의 모습·냄새에 대한 AI 감지를 차단합니다. 효과음과 게임 소음 게이지는 유지되며, 발포 감지는 별도입니다. 승하차 같은 상태 전환에는 잠시 대기 후 자동으로 다시 적용합니다.': 'Blocks AI detection of movement and vehicle noise, and player visibility and scent. Sound effects and the game noise meter stay unchanged; gunshot detection is separate. Automatically reapplies after transitions such as entering or leaving a vehicle.',
    '일부 게임 스레드 재개에 실패했습니다': 'Could not resume some game threads',
    '잘못된 윤곽 주소입니다': 'The outline address is invalid',
    '전체 OFF': 'All OFF',
    '전체 OFF · 0/6': 'All OFF · 0/6',
    '전체 ON': 'All ON',
    '전체 동물 흔적 숨김을 유지하면서 반려견 윤곽만 표시합니다. 게임의 사냥개 윤곽 켜기·색상과 원래 가림 판정을 따릅니다. 닌자 효과는 반려견에도 유지됩니다.': 'Keeps all animal clues hidden while showing the dog outline. Uses the native dog outline setting, color, and occlusion rules. Ninja effects still apply to the dog.',
    '전체 모드': 'All modes',
    '중복 실행 상태를 확인하지 못해 모드를 시작하지 않았습니다': 'Could not check for another instance; the app was not started',
    '지금은 확인할 수 없습니다. 잠시 후 다시 확인하세요.': 'Cannot check right now. Please try again later.',
    '지원하는 윤곽 색상은 blue 또는 white입니다': 'Supported outline colors are blue and white',
    '지원하지 않는 게임 버전입니다. 업데이트 확인 후 모드를 다시 실행하세요.': 'Unsupported game build. Check for updates, then restart the app.',
    '지원하지 않는 게임 파일이어서 닌자 모드를 시작하지 않았습니다': 'Ninja mode was not started: unsupported game executable',
    '지원하지 않는 게임 파일이어서 사체 훅을 설치하지 않았습니다': 'The carcass hook was not installed: unsupported game executable',
    '지원하지 않는 게임 파일입니다': 'Unsupported game executable',
    '차량 AI 입력 목록이 변경 중입니다': 'The vehicle AI input list is changing',
    '차량 승하차 연결이 변경 중입니다': 'The vehicle entry or exit binding is changing',
    '차량 확인 중 플레이어 연결이 변경 중입니다': 'The player binding changed while checking the vehicle',
    '최신 정식 배포를 확인하고 있습니다.': 'Checking the latest stable release.',
    '파랑': 'Blue',
    '플레이어 AI 입력 연결이 변경 중입니다': 'The player AI input binding is changing',
    '플레이어 감지 핸들 연결이 변경 중입니다': 'The player sensing handle binding is changing',
    '플레이어 감지 핸들이 변경 중입니다': 'The player sensing handle is changing',
    '플레이어 목록이 유효하지 않습니다': 'The player list is invalid',
    '플레이어 방향 갱신을 기다리고 있습니다': 'Waiting for the player direction to update',
    '플레이어 위치 갱신을 기다리고 있습니다': 'Waiting for the player position to update',
    '헬하운드 OFF': 'Hellhound OFF',
    '헬하운드 ON': 'Hellhound ON',
    '헬하운드 ON · 연결 대기': 'Hellhound ON · Waiting for connection',
    '헬하운드 모드 · 독립 ON/OFF': 'Hellhound mode · Independent ON/OFF',
    '헬하운드 모드 바이너리를 확인하지 못했습니다': 'Could not verify the Hellhound mode binary',
    '헬하운드 설치 실패: 원본 코드를 복원했습니다': 'Hellhound installation failed; original code restored',
    '헬하운드 설치와 복원에 실패했습니다. 게임을 종료하세요': 'Hellhound installation and restoration failed. Close the game.',
    '헬하운드 코드 기록 검증 실패': 'Hellhound patch verification failed',
    '헬하운드 코드가 검증된 버전과 다릅니다': 'The Hellhound code differs from the verified build',
    '헬하운드 코드가 다른 프로그램에 의해 변경되었습니다': 'Another program modified the Hellhound code',
    '헬하운드 호출 코드가 바뀌었습니다': 'The Hellhound call site changed',
    '헬하운드를 위한 게임 프로세스 접근 권한을 얻지 못했습니다': 'Could not access the game process for Hellhound mode',
    '현재 로컬 플레이어 연결이 변경 중입니다': 'The current local player binding is changing',
    '현재 차량 AI 입력 목록을 확인하지 못했습니다': 'Could not read the current vehicle AI input list',
    '현재 차량 AI 입력 연결이 변경 중입니다': 'The current vehicle AI input binding is changing',
    '현재 차량 감지 핸들이 변경 중입니다': 'The current vehicle sensing handle is changing',
    '현재 탑승 차량 연결이 변경 중입니다': 'The occupied vehicle binding is changing',
    '현재 탑승 차량 형식을 확인하지 못했습니다': 'Could not verify the occupied vehicle type',
    '현재 플레이어 연결이 변경 중입니다': 'The current player binding is changing',
    '현재 플레이어 캐릭터가 변경 중입니다': 'The current player character is changing',
    '현재 플레이어의 AI 입력이 변경 중입니다': 'The current player AI input is changing',
    '확인 불가': 'Unavailable',
    '확인 중에도 모드를 사용할 수 있습니다.': 'You can use the modes while the check runs.',
    '확인할 수 있는 정식 배포가 없습니다.': 'No stable release is available to check.',
    '활성 리트리버 작업을 기다리고 있습니다': 'Waiting for an active retriever task',
    '활성 반려견 연결을 기다리고 있습니다': 'Waiting for the active dog binding',
    '회수 위치가 유효하지 않습니다': 'The retrieval position is invalid',
    '흰색': 'White',
}

# Templates match the fully formatted text at UI boundaries, including nested
# status/color values. No backend state keys or native strings are modified.
TEMPLATES = {
    '{hotkey} · 단축키 등록 중': '{hotkey} · Registering hotkey',
    '{state} · 대상 {count}마리': '{state} · {count} targets',
    '{hotkey} · 전체 ON/OFF': '{hotkey} · All ON/OFF',
    '{color}을 선택했습니다. 모드 ON을 누르면 적용됩니다.': '{color} selected. Press Mode ON to apply it.',
    '게임을 실행하고 사냥터에 들어가세요. 감지된 게임: {count}개': 'Start the game and enter a reserve. Game processes found: {count}',
    '사체 색상: {color} · 변경': 'Carcass color: {color} · Change',
    '살아 있는 사냥감: {count}마리': 'Live animals: {count}',
    '살아 있는 사냥감의 {color} 윤곽을 갱신하고 있습니다.': 'Updating {color} outlines for live animals.',
    '일부 ON · {count}/6': 'Some ON · {count}/6',
    '전체 ON · {count}/6': 'All ON · {count}/6',
    '현재 {current} / 최신 {latest}': 'Current {current} / Latest {latest}',
    '현재 {current} / 최신 확인 중': 'Current {current} / Checking latest',
}

KO_NATIVE = {
    'AI calculation CALL changed during transaction': '소음기 AI 설치 중 호출 코드가 바뀌었습니다',
    'AI sound profile changed during binding': 'AI 소음 프로필 연결이 변경 중입니다',
    'AI sound profile is changing': 'AI 소음 프로필이 변경 중입니다',
    'AI sound profile manager is changing': 'AI 소음 프로필 관리자 연결이 변경 중입니다',
    'AI weapon profile tree invalid': 'AI 무기 프로필 목록이 유효하지 않습니다',
    'AI weapon profiles unavailable': 'AI 무기 프로필을 확인하지 못했습니다',
    'Foreign silencer AI patch': '소음기 AI 호출 코드가 다른 프로그램에 의해 변경되었습니다',
    'Invalid silencer AI allocation': '소음기 AI 메모리 위치가 유효하지 않습니다',
    'Native AI calculation differs': 'AI 소음 계산 코드가 검증된 버전과 다릅니다',
    'Native longbow AI profile differs': '원래 롱보우 AI 소음 프로필이 검증된 값과 다릅니다',
    'Native longbow AI profile missing': '원래 롱보우 AI 소음 프로필을 찾지 못했습니다',
    'Partial silencer AI patch': '소음기 AI 호출 코드 일부가 예상과 다릅니다',
    'Silencer AI binary mismatch': '소음기 AI 바이너리를 확인하지 못했습니다',
    'Silencer AI not attached': '소음기 AI 모드가 연결되지 않았습니다',
    'Silencer AI ownership mismatch': '소음기 AI 코드의 소유권을 확인하지 못했습니다',
    'Silencer AI rollback failed; stop the game': '소음기 AI 복원에 실패했습니다. 게임을 종료하세요',
    'Silencer AI transaction failed; previous calls restored': '소음기 AI 설치에 실패하여 이전 호출 코드를 복원했습니다',
    'Unsupported game executable': '지원하지 않는 게임 파일입니다',
    'Ambiguous silencer mapping': '소음기 오디오 대응표에 중복이 있습니다',
    'FMOD createInstance CALL changed during transaction': '소음기 오디오 설치 중 호출 코드가 바뀌었습니다',
    'Foreign FMOD createInstance CALL patch': '소음기 오디오 호출 코드가 다른 프로그램에 의해 변경되었습니다',
    'FMOD audio CALL changed during transaction': '소음기 오디오 생성·재생 설치 중 호출 코드가 바뀌었습니다',
    'Foreign FMOD audio CALL patch': '소음기 오디오 생성·재생 호출 코드가 다른 프로그램에 의해 변경되었습니다',
    'Partial FMOD audio patch': '소음기 오디오 생성·재생 코드가 일부만 설치되었습니다',
    'Invalid silencer allocation': '소음기 오디오 메모리 위치가 유효하지 않습니다',
    'Silencer audio binary/mapping mismatch': '소음기 오디오 바이너리와 대응표를 확인하지 못했습니다',
    'Silencer audio is not installed': '소음기 오디오 모드가 설치되지 않았습니다',
    'Silencer audio native signature mismatch': '오디오 생성 코드가 검증된 버전과 다릅니다',
    'Silencer audio ownership mismatch': '소음기 오디오 코드의 소유권을 확인하지 못했습니다',
    'Silencer postimage mismatch': '소음기 호출 코드 기록 검증에 실패했습니다',
    'Silencer rollback failed; stop the game': '소음기 오디오 복원에 실패했습니다. 게임을 종료하세요',
    'Silencer rollback mismatch': '소음기 오디오 복원 검증에 실패했습니다',
    'Silencer transaction failed; previous CALL restored': '소음기 오디오 설치에 실패하여 이전 호출 코드를 복원했습니다',
    'Unsupported silencer mapping': '지원하지 않는 소음기 오디오 대응표입니다',
    'Silencer audio replacement failed; original sounds have been restored': '소음기 오디오 치환에 실패하여 원래 소리로 복원했습니다',
}
EN.update({korean:english for english, korean in KO_NATIVE.items()})


def _patterns(catalog):
    result = []
    # More literal text wins over a generic template with the same prefix.
    ordered = sorted(catalog.items(), key=lambda item:sum(len(part[0]) for part in Formatter().parse(item[0])), reverse=True)
    for source, target in ordered:
        parts, fields = [], []
        for literal, name, _, _ in Formatter().parse(source):
            parts.append(re.escape(literal))
            if name is not None:
                fields.append(name)
                parts.append('(.+?)')
        result.append((re.compile(''.join(parts), re.DOTALL), target, fields))
    return result


_EN_PATTERNS = _patterns(TEMPLATES)
_KO_PATTERNS = _patterns({target:source for source, target in TEMPLATES.items()})
_KO = {target:source for source, target in EN.items()}
_KO.update(KO_NATIVE)


def tr(text, lang=None):
    """Translate known app UI text; preserve unknown diagnostic details verbatim."""
    language = LANGUAGE if lang is None else ('ko' if str(lang).lower() == 'ko' else 'en')
    return _translate(text, language, 0)


def _translate(text, language, depth):
    if not isinstance(text, str):
        return text
    catalog = _KO if language == 'ko' else EN
    if text in catalog:
        return catalog[text]
    if depth >= 4:
        return text
    for pattern, target, fields in _KO_PATTERNS if language == 'ko' else _EN_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            values = {name:_translate(value, language, depth + 1) for name, value in zip(fields, match.groups())}
            return target.format_map(values)
    return text
