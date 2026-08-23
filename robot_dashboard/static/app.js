import { api, latestApi } from './core/api.js';
import { $, setStatePill } from './core/dom.js';
import { formatHz, safeNumber } from './core/format.js';
import { captureStickyLogScroll, scheduleStickyLogScroll } from './core/log_scroll.js';
import { LidarSourceIdentity } from './features/sensors/lidar_identity.js';
import { initializeServiceLifecycleFeature } from './features/settings/service_lifecycle.js';
import { initializeControlBridgeServiceFeature } from './features/control/bridge_service.js';
import { initializeNavigationLogFeature } from './features/navigation/log_controller.js';
import { createDatasetFeature } from './features/datasets/capture.js';
import { createDiagnosticsExportFeature } from './features/settings/diagnostics.js';

// Exposed for the lightweight Node contract test and browser diagnostics.
window.RobotLidarSourceIdentity = LidarSourceIdentity;

const ui = {
  connectionChip: $('#connectionChip'),
  connectionLabel: $('#connectionLabel'),
  robotType: $('#robotType'),
  robotTypeNote: $('#robotTypeNote'),
  discoverRobotsButton: $('#discoverRobotsButton'),
  robotDiscoveryStatus: $('#robotDiscoveryStatus'),
  robotDiscoveryResults: $('#robotDiscoveryResults'),
  selectedRobotModel: $('#selectedRobotModel'),
  selectedRobotUrdf: $('#selectedRobotUrdf'),
  robotIp: $('#robotIp'),
  connectButton: $('#connectButton'),
  disconnectButton: $('#disconnectButton'),
  connectedRobotTarget: $('#connectedRobotTarget'),
  agentHost: $('#agentHost'),
  rosRuntime: $('#rosRuntime'),
  rosDomain: $('#rosDomain'),
  topicCount: $('#topicCount'),
  profileLabel: $('#profileLabel'),
  pageTitle: $('#pageTitle'),
  pageDescription: $('#pageDescription'),
  linkMetric: $('#linkMetric'),
  linkSub: $('#linkSub'),
  cameraMetric: $('#cameraMetric'),
  cameraSub: $('#cameraSub'),
  lidarMetric: $('#lidarMetric'),
  lidarSub: $('#lidarSub'),
  batteryMetric: $('#batteryMetric'),
  batterySub: $('#batterySub'),
  cameraSource: $('#cameraSource'),
  cameraSingleMode: $('#cameraSingleMode'),
  cameraDualMode: $('#cameraDualMode'),
  cameraPrimarySource: $('#cameraPrimarySource'),
  cameraCapacity: $('#cameraCapacity'),
  cameraViewGrid: $('#cameraViewGrid'),
  cameraPrimarySlot: $('#cameraPrimarySlot'),
  cameraPrimaryLabel: $('#cameraPrimaryLabel'),
  cameraPrimarySourceId: $('#cameraPrimarySourceId'),
  cameraPrimaryState: $('#cameraPrimaryState'),
  cameraPrimaryFps: $('#cameraPrimaryFps'),
  cameraPrimaryTopic: $('#cameraPrimaryTopic'),
  cameraPrimaryTransport: $('#cameraPrimaryTransport'),
  cameraSecondarySlot: $('#cameraSecondarySlot'),
  cameraSecondaryCanvas: $('#cameraSecondaryCanvas'),
  cameraSecondaryEmpty: $('#cameraSecondaryEmpty'),
  cameraSecondaryEmptyText: $('#cameraSecondaryEmptyText'),
  cameraSecondaryLabel: $('#cameraSecondaryLabel'),
  cameraSecondarySourceId: $('#cameraSecondarySourceId'),
  cameraSecondaryState: $('#cameraSecondaryState'),
  cameraSecondaryFps: $('#cameraSecondaryFps'),
  cameraSecondaryTopic: $('#cameraSecondaryTopic'),
  cameraSecondaryTransport: $('#cameraSecondaryTransport'),
  cameraSecondaryTopicLabel: $('#cameraSecondaryTopicLabel'),
  cameraSecondaryCodecLabel: $('#cameraSecondaryCodecLabel'),
  cloudSource: $('#cloudSource'),
  cloudSourceSensorBadge: $('#cloudSourceSensorBadge'),
  cloudSourcePin: $('#cloudSourcePin'),
  cloudSourceTopicLabel: $('#cloudSourceTopicLabel'),
  cloudSourceStageLabel: $('#cloudSourceStageLabel'),
  cloudSourceFreshness: $('#cloudSourceFreshness'),
  odomSource: $('#odomSource'),
  mapSource: $('#mapSource'),
  serviceLifecycleState: $('#serviceLifecycleState'),
  serviceLifecycleName: $('#serviceLifecycleName'),
  serviceLifecycleInstance: $('#serviceLifecycleInstance'),
  serviceLifecyclePrivilege: $('#serviceLifecyclePrivilege'),
  serviceLifecycleOperation: $('#serviceLifecycleOperation'),
  serviceLifecycleConfirm: $('#serviceLifecycleConfirm'),
  serviceRestartButton: $('#serviceRestartButton'),
  serviceStopButton: $('#serviceStopButton'),
  serviceLifecycleMessage: $('#serviceLifecycleMessage'),
  cameraCanvas: $('#cameraCanvas'),
  cameraEmpty: $('#cameraEmpty'),
  cameraEmptyText: $('#cameraEmptyText'),
  cameraState: $('#cameraState'),
  cameraTopicLabel: $('#cameraTopicLabel'),
  cameraCodecLabel: $('#cameraCodecLabel'),
  cameraMediaStatus: $('#cameraMediaStatus'),
  cameraMediaHelp: $('#cameraMediaHelp'),
  cameraRecordDuration: $('#cameraRecordDuration'),
  cameraCaptureFormat: $('#cameraCaptureFormat'),
  cameraCaptureButton: $('#cameraCaptureButton'),
  cameraRecordButton: $('#cameraRecordButton'),
  cameraStopRecordButton: $('#cameraStopRecordButton'),
  sceneCanvas: $('#sceneCanvas'),
  liveMap2dCanvas: $('#liveMap2dCanvas'),
  mapCanvas: $('#mapCanvas'),
  mapGridOverlay: $('#mapGridOverlay'),
  sceneControls: $('#sceneControls'),
  sceneResetButton: $('#sceneResetButton'),
  sceneTopButton: $('#sceneTopButton'),
  sceneFrontButton: $('#sceneFrontButton'),
  sceneFollowButton: $('#sceneFollowButton'),
  liveMap2dControls: $('#liveMap2dControls'),
  liveMap2dFitButton: $('#liveMap2dFitButton'),
  liveMap2dAutoFitButton: $('#liveMap2dAutoFitButton'),
  liveMap2dFollowButton: $('#liveMap2dFollowButton'),
  liveProjectionLegend: $('#liveProjectionLegend'),
  mapViewMode: $('#mapViewMode'),
  livePointBudget: $('#livePointBudget'),
  livePointCustomWrap: $('#livePointCustomWrap'),
  livePointCustom: $('#livePointCustom'),
  livePointApply: $('#livePointApply'),
  mapOverlayToggle: $('#mapOverlayToggle'),
  mappingState: $('#mappingState'),
  mappingLidarSensorBadge: $('#mappingLidarSensorBadge'),
  mappingLidarPin: $('#mappingLidarPin'),
  mappingLidarTopic: $('#mappingLidarTopic'),
  mappingLidarStage: $('#mappingLidarStage'),
  mappingLidarFreshness: $('#mappingLidarFreshness'),
  liveModelState: $('#liveModelState'),
  mapFrame: $('#mapFrame'),
  mapPoints: $('#mapPoints'),
  savedSceneCanvas: $('#savedSceneCanvas'),
  savedMapCanvas: $('#savedMapCanvas'),
  savedMapGridOverlay: $('#savedMapGridOverlay'),
  savedSceneControls: $('#savedSceneControls'),
  savedSceneResetButton: $('#savedSceneResetButton'),
  savedSceneTopButton: $('#savedSceneTopButton'),
  savedSceneFrontButton: $('#savedSceneFrontButton'),
  savedMapViewMode: $('#savedMapViewMode'),
  savedPointBudget: $('#savedPointBudget'),
  savedPointCustomWrap: $('#savedPointCustomWrap'),
  savedPointCustom: $('#savedPointCustom'),
  savedPointApply: $('#savedPointApply'),
  savedMapOverlayToggle: $('#savedMapOverlayToggle'),
  savedMappingState: $('#savedMappingState'),
  savedModelState: $('#savedModelState'),
  savedMapFrame: $('#savedMapFrame'),
  savedMapPoints: $('#savedMapPoints'),
  savedMapCount: $('#savedMapCount'),
  savedMapList: $('#savedMapList'),
  savedMapTitle: $('#savedMapTitle'),
  savedMapSource: $('#savedMapSource'),
  savedMapDetailFrame: $('#savedMapDetailFrame'),
  savedMapDetailPoints: $('#savedMapDetailPoints'),
  savedMapBounds: $('#savedMapBounds'),
  savedMapNameInput: $('#savedMapNameInput'),
  savedMapRenameButton: $('#savedMapRenameButton'),
  savedMapDeleteButton: $('#savedMapDeleteButton'),
  savedMapManageNote: $('#savedMapManageNote'),
  mapConvertState: $('#mapConvertState'),
  mapConvertSource: $('#mapConvertSource'),
  mapConvertName: $('#mapConvertName'),
  mapConvertZMin: $('#mapConvertZMin'),
  mapConvertZMax: $('#mapConvertZMax'),
  mapConvertResolution: $('#mapConvertResolution'),
  mapConvertRadius: $('#mapConvertRadius'),
  mapConvertNeighbors: $('#mapConvertNeighbors'),
  mapConvertBackground: $('#mapConvertBackground'),
  mapConvertStart: $('#mapConvertStart'),
  mapConvertProgress: $('#mapConvertProgress'),
  mapConvertProgressLabel: $('#mapConvertProgressLabel'),
  mapConvertMessage: $('#mapConvertMessage'),
  mapEditorState: $('#mapEditorState'),
  mapEditorCanvas: $('#mapEditorCanvas'),
  mapEditorEmpty: $('#mapEditorEmpty'),
  mapEditorBrushSize: $('#mapEditorBrushSize'),
  mapEditorBrushOutput: $('#mapEditorBrushOutput'),
  mapEditorUndo: $('#mapEditorUndo'),
  mapEditorRedo: $('#mapEditorRedo'),
  mapEditorReset: $('#mapEditorReset'),
  mapEditorSource: $('#mapEditorSource'),
  mapEditorStats: $('#mapEditorStats'),
  mapEditorSaveName: $('#mapEditorSaveName'),
  mapEditorSave: $('#mapEditorSave'),
  mapEditorMessage: $('#mapEditorMessage'),
  navigationSafetyBanner: $('#navigationSafetyBanner'),
  navigationSafetyTitle: $('#navigationSafetyTitle'),
  navigationSafetyMessage: $('#navigationSafetyMessage'),
  navigationControlLink: $('#navigationControlLink'),
  navigationPipelineState: $('#navigationPipelineState'),
  navigationPipelineNote: $('#navigationPipelineNote'),
  navigationRobotState: $('#navigationRobotState'),
  navigationRobotNote: $('#navigationRobotNote'),
  navigationLocalizationState: $('#navigationLocalizationState'),
  navigationLocalizationNote: $('#navigationLocalizationNote'),
  navigationGoalState: $('#navigationGoalState'),
  navigationGoalNote: $('#navigationGoalNote'),
  navigationMapState: $('#navigationMapState'),
  navigationMapSelect: $('#navigationMapSelect'),
  navigationStartButton: $('#navigationStartButton'),
  navigationStopButton: $('#navigationStopButton'),
  navigationMapCanvas: $('#navigationMapCanvas'),
  navigationMapEmpty: $('#navigationMapEmpty'),
  navigationMapHint: $('#navigationMapHint'),
  navigationInitialPoseTool: $('#navigationInitialPoseTool'),
  navigationGoalPoseTool: $('#navigationGoalPoseTool'),
  navigationPoseMode: $('#navigationPoseMode'),
  navigationPoseCoordinates: $('#navigationPoseCoordinates'),
  navigationPoseDiscard: $('#navigationPoseDiscard'),
  navigationPoseSend: $('#navigationPoseSend'),
  mapAnnotationState: $('#mapAnnotationState'),
  mapAnnotationType: $('#mapAnnotationType'),
  mapAnnotationName: $('#mapAnnotationName'),
  mapAnnotationDraw: $('#mapAnnotationDraw'),
  mapAnnotationFinish: $('#mapAnnotationFinish'),
  mapAnnotationCancel: $('#mapAnnotationCancel'),
  mapAnnotationList: $('#mapAnnotationList'),
  mapAnnotationMessage: $('#mapAnnotationMessage'),
  mapAnnotationDiscard: $('#mapAnnotationDiscard'),
  mapAnnotationSave: $('#mapAnnotationSave'),
  navigationJobId: $('#navigationJobId'),
  navigationReadiness: $('#navigationReadiness'),
  navigationGoalDistance: $('#navigationGoalDistance'),
  navigationGoalElapsed: $('#navigationGoalElapsed'),
  navigationGoalRecoveries: $('#navigationGoalRecoveries'),
  navigationGoalProgress: $('#navigationGoalProgress'),
  navigationGoalMessage: $('#navigationGoalMessage'),
  navigationCancelGoal: $('#navigationCancelGoal'),
  navigationClearCostmaps: $('#navigationClearCostmaps'),
  navigationHealthState: $('#navigationHealthState'),
  navigationHealthReason: $('#navigationHealthReason'),
  navigationHealthMetrics: $('#navigationHealthMetrics'),
  navigationCalibrationList: $('#navigationCalibrationList'),
  navigationLogPhase: $('#navigationLogPhase'),
  navigationLogRuntimeState: $('#navigationLogRuntimeState'),
  navigationLogTimestamp: $('#navigationLogTimestamp'),
  navigationLogAutoScroll: $('#navigationLogAutoScroll'),
  navigationLogClear: $('#navigationLogClear'),
  navigationLogOutput: $('#navigationLogOutput'),
  navigationLogEmpty: $('#navigationLogEmpty'),
  navigationLogNotice: $('#navigationLogNotice'),
  navigationModelState: $('#navigationModelState'),
  navigationRobotCanvas: $('#navigationRobotCanvas'),
  navigationRobotControls: $('#navigationRobotControls'),
  navigationRobotResetButton: $('#navigationRobotResetButton'),
  navigationRobotTopButton: $('#navigationRobotTopButton'),
  navigationRobotFrontButton: $('#navigationRobotFrontButton'),
  navigationRobotAxesButton: $('#navigationRobotAxesButton'),
  navigationModelLabel: $('#navigationModelLabel'),
  navigationModelNote: $('#navigationModelNote'),
  navigationParameterState: $('#navigationParameterState'),
  navigationPreset: $('#navigationPreset'),
  navigationPresetLoad: $('#navigationPresetLoad'),
  navigationParameterReset: $('#navigationParameterReset'),
  navigationParameterApply: $('#navigationParameterApply'),
  navigationParameterDirty: $('#navigationParameterDirty'),
  navigationParameterGroups: $('#navigationParameterGroups'),
  navigationScanBinding: $('#navigationScanBinding'),
  navigationOdomBinding: $('#navigationOdomBinding'),
  navigationParameterMessage: $('#navigationParameterMessage'),
  liveCloudTopic: $('#liveCloudTopic'),
  liveCloudStatus: $('#liveCloudStatus'),
  liveOdomTopic: $('#liveOdomTopic'),
  liveOdomStatus: $('#liveOdomStatus'),
  liveMapTopic: $('#liveMapTopic'),
  liveMapStatus: $('#liveMapStatus'),
  mappingControlState: $('#mappingControlState'),
  mappingSessionName: $('#mappingSessionName'),
  mappingCreate2d: $('#mappingCreate2d'),
  mappingStartButton: $('#mappingStartButton'),
  mappingSaveButton: $('#mappingSaveButton'),
  mappingStopButton: $('#mappingStopButton'),
  mappingPipelineLabel: $('#mappingPipelineLabel'),
  mappingDataLabel: $('#mappingDataLabel'),
  mappingSaveLabel: $('#mappingSaveLabel'),
  mappingOperationMessage: $('#mappingOperationMessage'),
  mappingLog: $('#mappingLog'),
  sensorGrid: $('#sensorGrid'),
  sensorCount: $('#sensorCount'),
  odomTopic: $('#odomTopic'),
  posX: $('#posX'), posY: $('#posY'), posZ: $('#posZ'), speed: $('#speed'),
  topicsBody: $('#topicsBody'),
  topicSearch: $('#topicSearch'),
  categoryFilter: $('#categoryFilter'),
  lastUpdated: $('#lastUpdated'),
  toast: $('#toast'),
};

const controlUi = {
  profileNotice: $('#controlProfileNotice'),
  profileNoticeText: $('#controlProfileNoticeText'),
  availability: $('#controlAvailability'),
  availabilityNote: $('#controlAvailabilityNote'),
  leaseState: $('#controlLeaseState'),
  leaseNote: $('#controlLeaseNote'),
  bridgeState: $('#controlBridgeState'),
  bridgeNote: $('#controlBridgeNote'),
  bridgeServiceState: $('#controlBridgeServiceState'),
  bridgeServiceName: $('#controlBridgeServiceName'),
  bridgeServiceActive: $('#controlBridgeServiceActive'),
  bridgeServiceSub: $('#controlBridgeServiceSub'),
  bridgeServiceOperation: $('#controlBridgeServiceOperation'),
  bridgeServiceConfirm: $('#controlBridgeServiceConfirm'),
  bridgeServiceStart: $('#controlBridgeServiceStart'),
  bridgeServiceStop: $('#controlBridgeServiceStop'),
  bridgeServiceMessage: $('#controlBridgeServiceMessage'),
  estopStatusCard: $('#estopStatusCard'),
  estopState: $('#controlEstopState'),
  estopNote: $('#controlEstopNote'),
  statePill: $('#controlStatePill'),
  inputSource: $('#controlInputSource'),
  gamepadWrap: $('#gamepadDeviceWrap'),
  gamepad: $('#gamepadDevice'),
  deviceIndicator: $('#controlDeviceIndicator'),
  deviceStatus: $('#controlDeviceStatus'),
  arm: $('#controlArmButton'),
  disarm: $('#controlDisarmButton'),
  speed: $('#controlSpeedScale'),
  speedOutput: $('#controlSpeedOutput'),
  keyboardGuide: $('#keyboardControlGuide'),
  gamepadGuide: $('#gamepadControlGuide'),
  touchController: $('#touchController'),
  commandX: $('#controlCommandX'),
  commandY: $('#controlCommandY'),
  commandZ: $('#controlCommandZ'),
  commandXBar: $('#controlCommandXBar'),
  commandYBar: $('#controlCommandYBar'),
  commandZBar: $('#controlCommandZBar'),
  deadmanState: $('#controlDeadmanState'),
  deadmanMonitor: $('.deadman-monitor'),
  commandSource: $('#controlCommandSource'),
  estop: $('#softwareEstopButton'),
  clearConfirm: $('#estopClearConfirm'),
  clear: $('#estopClearButton'),
  actions: $('#controlActions'),
};

let latestState = null;
let stateRequestGeneration = 0;
let overviewTelemetryAvailability = null;
let latestTopics = [];
let sourceFingerprint = '';
let pointcloudSourceCatalog = new Map();
let pointcloudSourcesLoaded = false;
let pointcloudSelection = {};
let cameraSocket = null;
let cameraSocketGeneration = 0;
let cameraReconnectTimer = 0;
let jointSocket = null;
let poseSocket = null;
let cameraMeta = null;
let cameraStatusMeta = null;
let videoDecoder = null;
let cameraHasKey = false;
let cameraFrames = 0;
let cameraFrameWindow = [];
let cameraLastFrameAt = 0;
let cameraActiveSourceKey = '';
let cameraRecording = null;
let cameraImageDecodeQueue = null;
let cameraCatalog = [];
let cameraCatalogRequestGeneration = 0;
let cameraMaxActive = 1;
let cameraViewMode = 'single';
let cameraPrimarySourceId = '';
let cameraSecondarySourceId = '';
let cameraSlotRuntimes = null;
let cloudSeq = -1;
let pointcloudRequestInFlight = false;
let pointcloudRequestGeneration = 0;
let pointcloudSocket = null;
let pointcloudSocketGeneration = 0;
let pointcloudPendingFrame = null;
let pointcloudFrameScheduled = false;
let pointcloudReconnectTimer = 0;
let pointcloudLastFrameAt = 0;
let pointcloudBinaryHttpAvailable = true;
let pointcloudStreamId = '';
let mapSeq = -1;
let toastTimer = null;
let currentPose = null;
let targetPose = null;
let poseLive = false;
let lastPoseAt = 0;
let lastMotionFrameAt = 0;
let poseImuAnchor = null;
let lastPoseSignature = '';
let poseTrail = [];
let lastCloudSnapshot = null;
const liveCloudReservoir = window.RobotPointCloudStream?.RegisteredCloudReservoir
  ? new window.RobotPointCloudStream.RegisteredCloudReservoir(1000000)
  : null;
let livePointLimit = 10000;
let savedPointLimit = null;
let livePointBudgetBusy = false;
let savedPointBudgetBusy = false;
let savedMapMutationBusy = false;
let offlineCloudSnapshot = null;
let lastMapSnapshot = null;
let savedOccupancySnapshot = null;
let savedMapCatalog = [];
let selectedSavedMapId = '';
let selectedSavedMapMeta = null;
const savedMapDataCache = new Map();
const savedMapLoadPromises = new Map();
let savedMapSelectionGeneration = 0;
const mapEditorEngine = window.RobotMapEditor;
const MAP_CONVERSION_TRACKING_TIMEOUT_MS = 15 * 60 * 1000;
let mapConversionPending = null;
let mapConversionCompleting = false;
let mapConversionNameDirty = false;
let mapConversionSourceFingerprint = '';
let mapConversionFeedback = null;
let mapEditorSession = null;
let mapEditorTool = 'brush';
let mapEditorCellValue = 100;
let mapEditorBusy = false;
let mapEditorRenderFrame = 0;
let mapEditorFeedback = null;
let mapEditorUnavailableReason = '편집할 저장 2D 지도를 선택하세요.';
let activePage = 'overview';
let activeMapView = null;
let mapViewPreference = 'cloud';
let savedMapViewPreference = 'cloud';
let mapOverlayVisible = true;
let savedMapOverlayVisible = true;
let sceneCloudDataKey = '';
let sceneCloudSourceKey = '';
let liveMap2dDataKey = '';
let liveMap2dSourceKey = '';
let savedSceneCloudDataKey = '';
let savedSceneCloudSourceKey = '';
let liveSceneHadCloud = false;
let robotModelsReady = false;
let robotModelsFailed = false;
let robotModelLoadGeneration = 0;
let robotTypes = [];
let selectedRobotType = 'go2';
let selectedRobotCandidate = null;
let robotDiscoveryBusy = false;
let robotTypeDirty = false;
let robotIpDirty = false;
let robotDiscoveryGeneration = 0;
let robotDiscoveryController = null;
let robotConnectionBusy = false;
let robotTargetConnected = false;
let robotRuntimeDataCompatible = true;
let navigationModelPanelKey = '';
let jointLive = false;
let lastJointAt = 0;
let latestBodyRpy = null;
let targetJointPositions = null;
let renderedJointPositions = null;
let mappingControlSnapshot = null;
let mappingLogCursor = 0;
let mappingLogLines = [];
let handledMappingOperation = '';
let mappingControlRequestGeneration = 0;
const navigationEngine = window.RobotNavigation;
let navigationSnapshot = null;
let navigationStatusBusy = false;
let navigationStatusRequestGeneration = 0;
let navigationOperationBusy = false;
let navigationOperationKind = '';
let navigationApiAvailable = null;
const NAVIGATION_STARTUP_PHASES = Object.freeze({
  starting_localization: Object.freeze({ label: 'STARTING LOCALIZATION', message: '위치추정용 XT16·FAST-LIO 파이프라인을 시작하고 있습니다.', tone: 'waiting' }),
  waiting_localization: Object.freeze({ label: 'WAITING SENSOR', message: 'XT16·FAST-LIO 센서 데이터가 안정화되기를 기다리고 있습니다.', tone: 'waiting' }),
  starting_navigation: Object.freeze({ label: 'STARTING NAV2', message: '위치추정 입력을 확인했습니다. Nav2 프로세스를 시작하고 있습니다.', tone: 'waiting' }),
  warming_navigation: Object.freeze({ label: 'WARMING', message: 'Nav2가 scan·odometry·runtime health 안전 게이트를 확인하고 있습니다.', tone: 'waiting' }),
  activating: Object.freeze({ label: 'ACTIVATING', message: '최종 안전 점검 후 Navigation 제어 권한을 활성화하고 있습니다.', tone: 'waiting' }),
  active: Object.freeze({ label: 'RUNNING', message: 'Nav2가 실행 중입니다. 지도에서 초기 위치를 지정할 수 있습니다.', tone: 'ok' }),
  stopping: Object.freeze({ label: 'STOPPING', message: '시작 작업과 Navigation 소유 리소스를 안전하게 정리하고 있습니다.', tone: 'waiting' }),
  failed: Object.freeze({ label: 'FAILED', message: 'Navigation 시작에 실패했습니다. 아래 오류와 Navigation 로그를 확인하세요.', tone: 'error' }),
});
let navigationLogFeature = null;
let navigationParameterSnapshot = null;
let navigationParameterDraft = null;
let navigationParameterBusy = false;
let navigationSelectedMapMeta = null;
let navigationMapSnapshot = null;
let navigationMapError = '';
let navigationMapLoadGeneration = 0;
let navigationMapSourceCanvas = null;
let navigationMapCells = null;
let navigationMapLayout = null;
let navigationMapTool = '';
let navigationStagedPose = null;
let navigationPointer = null;
let navigationRenderFrame = 0;
let mapAnnotationFeature = null;
let serviceLifecycleFeature = null;
let controlBridgeServiceFeature = null;
let datasetFeature = null;
const controlInput = window.RobotControlInput;
const mapAnnotationEngine = window.RobotMapAnnotations;
const CONTROL_SOCKET_MAX_BUFFER_BYTES = 4096;
const CONTROL_SOCKET_BACKPRESSURE_GRACE_MS = 100;
let controlSnapshot = null;
let controlLeaseId = '';
let controlLeaseSource = '';
let controlSocket = null;
let controlSocketBound = false;
let controlBackpressureSince = null;
const intentionallyClosedControlSockets = new WeakSet();
let controlSequence = 0;
let lastControlHeartbeatAt = 0;
let controlDisarmBusy = false;
let controlEmergencyBusy = false;
let controlArmBusy = false;
let controlArmGeneration = 0;
let controlActionBusy = false;
let controlActionAckTimer = null;
let pendingControlActionId = '';
let controlSpeedInitialized = false;
let controlHadDeadman = false;
let controlMotionFrameActive = false;
let controlLastCommand = null;
let selectedGamepadIndex = '';
let gamepadEstopPressed = false;
let actionConfirmation = null;
const controlPressedKeys = new Set();
const controlPointerDirections = new Map();
const controlDeadmanPointers = new Set();

const scene3d = window.RobotScene3D && ui.sceneCanvas
  ? new window.RobotScene3D(ui.sceneCanvas, {
      maxPoints: 10000,
      maxCloudRadius: 150,
      pointSize: 0.05,
      autoFitOnFirstCloud: true,
    })
  : null;

if (scene3d) {
  scene3d.bindControls({
    reset: ui.sceneResetButton,
    top: ui.sceneTopButton,
    front: ui.sceneFrontButton,
    follow: ui.sceneFollowButton,
  });
  scene3d.setStatus({ online: false, lidarOnline: false, snapshot: false, message: '실시간 LiDAR 신호를 기다리고 있습니다' });
}

const liveMap2d = window.RobotLiveMap2D?.LiveMap2DRenderer && ui.liveMap2dCanvas
  ? new window.RobotLiveMap2D.LiveMap2DRenderer(ui.liveMap2dCanvas, {
      resolution: 0.08,
      maxCells: 50000,
      maxPixelRatio: 2,
    })
  : null;

if (liveMap2d) {
  liveMap2d.bindControls({
    fit: ui.liveMap2dFitButton,
    autoFit: ui.liveMap2dAutoFitButton,
    follow: ui.liveMap2dFollowButton,
  });
}

const savedScene3d = window.RobotScene3D && ui.savedSceneCanvas
  ? new window.RobotScene3D(ui.savedSceneCanvas, {
      maxPoints: null,
      maxCloudRadius: 1000000,
      pointSize: 0.05,
      autoFitOnFirstCloud: true,
    })
  : null;

if (savedScene3d) {
  savedScene3d.bindControls({
    reset: ui.savedSceneResetButton,
    top: ui.savedSceneTopButton,
    front: ui.savedSceneFrontButton,
  });
  savedScene3d.setStatus({ online: null, lidarOnline: null, snapshot: true, message: '저장 지도를 불러오는 중입니다' });
}

const navigationScene3d = window.RobotScene3D && ui.navigationRobotCanvas
  ? new window.RobotScene3D(ui.navigationRobotCanvas, {
      maxPoints: 100,
      maxCloudRadius: 20,
      autoFitOnFirstCloud: false,
      showTrail: false,
      axesStorageKey: 'robot-scope.navigation-model.axes.v1',
      initialDistance: 3,
    })
  : null;

if (navigationScene3d) {
  navigationScene3d.bindControls({
    reset: ui.navigationRobotResetButton,
    top: ui.navigationRobotTopButton,
    front: ui.navigationRobotFrontButton,
    axes: ui.navigationRobotAxesButton,
  });
  navigationScene3d.setRobotPose(null);
  navigationScene3d.setStatus({
    online: null,
    lidarOnline: null,
    snapshot: false,
    message: '선택한 로봇의 3D 모델을 준비하고 있습니다',
  });
}

function activeRobotProfile() {
  const profiles = robotTypes.length ? robotTypes : (window.RobotProfiles?.normalizeTypes?.([]) || []);
  return profiles.find((profile) => profile.id === selectedRobotType) || profiles[0] || null;
}

function modelBadgeLabel(profile = activeRobotProfile()) {
  return String(profile?.model?.label || profile?.label || 'ROBOT MODEL').trim().toUpperCase();
}

function modelFidelityNote(profile = activeRobotProfile()) {
  const fidelity = String(profile?.model?.fidelity || '').toLowerCase();
  if (fidelity.includes('generic') || fidelity.includes('approx')) return '범용 URDF 근사 모델 · 제조사 공식 모델 아님';
  if (fidelity.includes('official')) return '공식 URDF 기반 모델';
  return fidelity ? fidelity.replace(/[-_]/g, ' ') : 'URDF 기반 3D 모델';
}

function updateControlProfileUx(profile = activeRobotProfile()) {
  const manualControlSupported = window.RobotProfiles?.profileSupports?.(profile, 'manual_control') === true;
  if (controlUi.profileNotice) controlUi.profileNotice.hidden = manualControlSupported;
  if (controlUi.profileNoticeText && !manualControlSupported) {
    controlUi.profileNoticeText.textContent = `${profile?.label || '이 로봇'}은 현재 상태 확인·센서·3D 모델만 지원하며, 주행과 모션 명령은 Go2에서만 사용할 수 있습니다.`;
  }
  renderControlStatus();
}

function updateLiveModelBadge() {
  const label = modelBadgeLabel();
  ui.liveModelState.classList.toggle('ready', robotModelsReady);
  ui.liveModelState.classList.toggle('fallback', robotModelsFailed);
  if (!robotRuntimeDataCompatible) ui.liveModelState.textContent = `${label} · RESTART REQUIRED`;
  else if (robotModelsFailed) ui.liveModelState.textContent = `${label} · FALLBACK`;
  else if (!robotModelsReady) ui.liveModelState.textContent = `${label} · LOADING`;
  else if (jointLive) ui.liveModelState.textContent = `${label} · JOINTS LIVE`;
  else ui.liveModelState.textContent = `${label} · READY`;
  updateNavigationModelPanel();
}

function navigationRobotOnline() {
  if (navigationApiAvailable === true && typeof navigationSnapshot?.robot_online === 'boolean') {
    return navigationSnapshot.robot_online;
  }
  return null;
}

function updateNavigationModelPanel({ force = false } = {}) {
  const profile = activeRobotProfile();
  if (!profile || !ui.navigationModelState || !ui.navigationModelLabel || !ui.navigationModelNote) return;
  const online = navigationRobotOnline();
  const compatible = robotRuntimeDataCompatible;
  const liveJoints = compatible && robotModelsReady && !robotModelsFailed && profile.id === 'go2' && jointLive;
  const panelKey = [
    profile.id,
    compatible ? 'compatible' : 'restart',
    robotModelsReady ? 'ready' : robotModelsFailed ? 'fallback' : 'loading',
    liveJoints ? 'joints' : 'static',
    online == null ? 'unknown' : online ? 'online' : 'offline',
  ].join(':');
  if (!force && navigationModelPanelKey === panelKey) return;
  navigationModelPanelKey = panelKey;

  ui.navigationModelLabel.textContent = `${profile.model?.label || profile.label} · ${modelFidelityNote(profile)}`;
  if (!compatible) {
    setStatePill(ui.navigationModelState, 'waiting', 'RESTART REQUIRED');
    ui.navigationModelNote.textContent = `${profile.label} 선택 모델의 정적 미리보기입니다. ROS 프로필을 다시 시작하기 전에는 기존 로봇의 관절·자세 데이터를 적용하지 않습니다.`;
  } else if (robotModelsFailed) {
    setStatePill(ui.navigationModelState, 'waiting', 'FALLBACK');
    ui.navigationModelNote.textContent = `${profile.label} asset을 불러오지 못해 안전한 대체 모델을 표시합니다. 실시간 관절 데이터는 공식 모델이 준비될 때까지 적용하지 않습니다.`;
  } else if (!robotModelsReady) {
    setStatePill(ui.navigationModelState, 'waiting', 'LOADING');
    ui.navigationModelNote.textContent = `${profile.label}에 선택된 3D asset을 불러오고 있습니다.`;
  } else if (liveJoints) {
    setStatePill(ui.navigationModelState, 'ok', 'JOINTS LIVE');
    ui.navigationModelNote.textContent = `${profile.label} 모델에 현재 로봇의 관절 상태를 반영하고 있습니다. 이 패널은 모델 확인용이며 지도 좌표는 위의 2D map canvas를 사용합니다.`;
  } else {
    setStatePill(ui.navigationModelState, 'ok', 'MODEL READY');
    ui.navigationModelNote.textContent = `${profile.label} 선택 모델의 정적 미리보기입니다. 로봇 관절 토픽이 정상이고 runtime 프로필이 일치하면 움직임이 자동으로 반영됩니다.`;
  }

  navigationScene3d?.setRobotVisible(true);
  navigationScene3d?.setRobotPose(null);
  if (!liveJoints) navigationScene3d?.resetRobotJointPositions?.();
  else if (renderedJointPositions) navigationScene3d?.setRobotJointPositions?.(renderedJointPositions);
  navigationScene3d?.setStatus({
    online: compatible ? online : null,
    lidarOnline: null,
    snapshot: false,
    message: !compatible
      ? 'ROS PROFILE RESTART REQUIRED · STATIC PREVIEW'
      : robotModelsFailed
        ? 'MODEL ASSET FALLBACK PREVIEW'
        : `${profile.label} 3D MODEL PREVIEW`,
  });
}

async function applyRobotModel(profile = activeRobotProfile()) {
  if (!profile) return;
  const generation = ++robotModelLoadGeneration;
  const assetUrl = String(profile.model?.asset_url || '').trim();
  const renderers = [
    { renderer: scene3d, poseOrigin: 'base', adaptiveScale: false },
    { renderer: savedScene3d, poseOrigin: 'ground', adaptiveScale: true },
    { renderer: navigationScene3d, poseOrigin: 'ground', adaptiveScale: true },
  ].filter((entry) => Boolean(entry.renderer));
  robotModelsReady = false;
  robotModelsFailed = false;
  navigationModelPanelKey = '';
  renderers.forEach(({ renderer, poseOrigin, adaptiveScale }) => {
    renderer._robotModelLabel = profile.label;
    renderer._robotModelType = profile.id;
    renderer.resetRobotJointPositions?.();
    renderer.configureOfficialRobot?.({
      enabled: Boolean(assetUrl),
      assetUrl,
      poseOrigin,
      adaptiveScale,
      scale: 1,
    });
  });
  if (ui.selectedRobotModel) ui.selectedRobotModel.textContent = `${profile.model?.label || profile.label} · ${modelFidelityNote(profile)}`;
  if (ui.selectedRobotUrdf) {
    const urdfUrl = String(profile.model?.urdf_url || '').trim();
    ui.selectedRobotUrdf.hidden = !urdfUrl;
    if (urdfUrl) ui.selectedRobotUrdf.href = urdfUrl;
    else ui.selectedRobotUrdf.removeAttribute('href');
  }
  ui.savedModelState.textContent = `${modelBadgeLabel(profile)} · LOADING`;
  ui.savedModelState.classList.remove('ready', 'fallback');
  updateLiveModelBadge();
  try {
    if (!assetUrl || !renderers.length || renderers.some(({ renderer }) => typeof renderer.loadOfficialRobotModel !== 'function')) {
      throw new Error('robot model renderer or asset is unavailable');
    }
    await Promise.all(renderers.map(({ renderer }) => renderer.loadOfficialRobotModel(assetUrl)));
    if (generation !== robotModelLoadGeneration) return;
    robotModelsReady = true;
    ui.savedModelState.textContent = modelBadgeLabel(profile);
    ui.savedModelState.classList.add('ready');
    updateLiveModelBadge();
  } catch (error) {
    if (generation !== robotModelLoadGeneration) return;
    console.warn(`${profile.label} model fallback:`, error);
    robotModelsFailed = true;
    ui.savedModelState.textContent = `${modelBadgeLabel(profile)} · FALLBACK`;
    ui.savedModelState.classList.add('fallback');
    updateLiveModelBadge();
  }
}

function renderRobotTypeOptions() {
  const fragment = document.createDocumentFragment();
  robotTypes.forEach((profile) => {
    const option = document.createElement('option');
    option.value = profile.id;
    option.textContent = profile.label;
    fragment.appendChild(option);
  });
  ui.robotType.replaceChildren(fragment);
  if (robotTypes.some((profile) => profile.id === selectedRobotType)) ui.robotType.value = selectedRobotType;
}

function clearRobotDiscovery(message = '네트워크 검색을 시작하면 연결 후보가 여기에 표시됩니다.') {
  selectedRobotCandidate = null;
  const empty = document.createElement('div');
  empty.className = 'robot-discovery-empty';
  empty.textContent = message;
  ui.robotDiscoveryResults.replaceChildren(empty);
}

function setDiscoveryStatus(message, error = false) {
  ui.robotDiscoveryStatus.textContent = message;
  ui.robotDiscoveryStatus.classList.toggle('error', error);
}

function cancelRobotDiscovery() {
  robotDiscoveryGeneration += 1;
  robotDiscoveryController?.abort();
  robotDiscoveryController = null;
  robotDiscoveryBusy = false;
  ui.discoverRobotsButton.disabled = false;
  ui.discoverRobotsButton.textContent = '네트워크 검색';
}

function selectRobotCandidate(candidate) {
  selectedRobotCandidate = candidate;
  robotIpDirty = true;
  ui.robotIp.value = candidate.ip;
  ui.robotDiscoveryResults.querySelectorAll('.robot-candidate').forEach((button) => {
    const selected = button.dataset.robotIp === candidate.ip;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-pressed', selected ? 'true' : 'false');
  });
}

function renderRobotCandidates(candidates) {
  if (!candidates.length) {
    clearRobotDiscovery('선택한 유형의 로봇을 찾지 못했습니다. 연결과 전원을 확인하거나 IP를 직접 입력하세요.');
    return;
  }
  const fragment = document.createDocumentFragment();
  candidates.forEach((candidate) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'robot-candidate';
    button.dataset.robotIp = candidate.ip;
    button.setAttribute('aria-pressed', 'false');
    const identity = document.createElement('span');
    const ip = document.createElement('strong');
    ip.textContent = candidate.ip;
    const host = document.createElement('small');
    const details = [candidate.hostname, candidate.interface, candidate.reason].filter(Boolean);
    host.textContent = details.join(' · ');
    identity.append(ip, host);
    const metric = document.createElement('em');
    const confidenceLabel = candidate.confidence == null
      ? '유형 미확인'
      : candidate.confidence >= 0.8
        ? '유형 일치'
        : candidate.confidence >= 0.4
          ? '네트워크 후보'
          : '미확인 호스트';
    const latencyLabel = candidate.latency_ms == null ? '응답 확인' : `${candidate.latency_ms.toFixed(1)} ms`;
    metric.textContent = `${confidenceLabel} · ${latencyLabel}`;
    button.title = details.join(' · ');
    button.append(identity, metric);
    button.addEventListener('click', () => selectRobotCandidate(candidate));
    fragment.appendChild(button);
  });
  ui.robotDiscoveryResults.replaceChildren(fragment);
}

async function discoverRobots() {
  const generation = ++robotDiscoveryGeneration;
  robotDiscoveryController?.abort();
  const controller = new AbortController();
  robotDiscoveryController = controller;
  robotDiscoveryBusy = true;
  selectedRobotCandidate = null;
  ui.discoverRobotsButton.disabled = true;
  ui.discoverRobotsButton.textContent = '검색 중…';
  setDiscoveryStatus('검색 중');
  clearRobotDiscovery('Jetson에 연결된 네트워크 인터페이스를 검색하고 있습니다…');
  try {
    const payload = await api('/api/v1/robots/discover', {
      method: 'POST',
      signal: controller.signal,
      body: JSON.stringify({ robot_type: selectedRobotType }),
    });
    if (generation !== robotDiscoveryGeneration) return;
    const candidates = window.RobotProfiles.normalizeDiscovery(payload);
    renderRobotCandidates(candidates);
    setDiscoveryStatus(candidates.length ? `${candidates.length}개 발견` : '후보 없음');
  } catch (error) {
    if (generation !== robotDiscoveryGeneration) return;
    if (error.name === 'AbortError') return;
    clearRobotDiscovery('자동 검색에 실패했습니다. IP를 직접 입력해 연결할 수 있습니다.');
    setDiscoveryStatus(`검색 실패 · ${error.message}`, true);
  } finally {
    if (generation === robotDiscoveryGeneration) {
      robotDiscoveryBusy = false;
      robotDiscoveryController = null;
      ui.discoverRobotsButton.disabled = false;
      ui.discoverRobotsButton.textContent = '다시 검색';
    }
  }
}

function activateRobotType(typeId, { discover = false, dirty = false } = {}) {
  const profile = robotTypes.find((candidate) => candidate.id === typeId) || robotTypes[0];
  if (!profile) return;
  const typeChanged = selectedRobotType !== profile.id;
  if (typeChanged) {
    cancelRobotDiscovery();
    robotRuntimeDataCompatible = false;
    resetLiveRobotSessionView();
  }
  selectedRobotType = profile.id;
  robotTypeDirty = dirty;
  markJointsStale(true);
  ui.robotType.value = profile.id;
  ui.robotTypeNote.textContent = `${profile.description || `${profile.label} 네트워크 설정을 사용합니다.`} · ${modelFidelityNote(profile)}`;
  clearRobotDiscovery();
  setDiscoveryStatus('검색 대기');
  applyRobotModel(profile);
  updateControlProfileUx(profile);
  if (discover) discoverRobots();
}

async function initializeRobotProfiles() {
  const profiles = window.RobotProfiles;
  if (!profiles) {
    showToast('로봇 유형 모듈을 불러오지 못했습니다.', true);
    return;
  }
  let payload = null;
  try {
    payload = await api('/api/v1/robots/types');
  } catch (error) {
    console.warn('Robot type catalog fallback:', error);
  }
  robotTypes = profiles.normalizeTypes(payload);
  selectedRobotType = profiles.robotTypeId(payload?.selected_type) || selectedRobotType;
  if (!robotTypes.some((profile) => profile.id === selectedRobotType)) selectedRobotType = robotTypes[0]?.id || 'go2';
  renderRobotTypeOptions();
  activateRobotType(selectedRobotType);
}

const PAGE_META = {
  overview: ['Overview', '로봇과 ROS 2 시스템의 전체 상태를 빠르게 확인합니다.'],
  mapping: ['Live LiDAR Mapping', '실시간 점군, 로봇 자세와 매핑 파이프라인을 확인합니다.'],
  maps: ['Saved Maps', '이미 매핑된 3D PCD와 2D 점유 지도를 센서 없이 탐색합니다.'],
  sensors: ['Sensors & Camera', '카메라 스트림과 로봇 센서 값을 기능별로 확인합니다.'],
  topics: ['ROS Graph', '발견된 ROS 2 토픽, 타입, 수신률과 지연을 조회합니다.'],
  controls: ['Robot Controls', 'ARM 버튼으로 제어 권한을 얻은 뒤 키보드·게임패드 주행과 허용된 Go2 동작을 실행합니다.'],
  navigation: ['Nav2 Navigation', '저장된 2D 지도에서 초기 위치와 목표를 지정하고 Go2 자율주행을 관리합니다.'],
  settings: ['Settings', '로봇 유형을 고르고 네트워크에서 연결 대상을 찾은 뒤 ROS 2 데이터 소스를 선택합니다.'],
};

function pageFromHash() {
  const route = location.hash.replace(/^#\/?/, '').trim();
  return Object.hasOwn(PAGE_META, route) ? route : 'overview';
}

function activatePage(page, updateHash = false) {
  const previousPage = activePage;
  const requestedPage = Object.hasOwn(PAGE_META, page) ? page : 'overview';
  if (previousPage === 'maps' && requestedPage !== 'maps' && editorHasUnsavedChanges()) {
    if (!confirmDiscardMapEditor('저장하지 않은 2D 지도 편집을 버리고 화면을 이동할까요?')) {
      history.replaceState(null, '', '#maps');
      return;
    }
    detachMapEditor('편집할 저장 2D 지도를 선택하세요.');
  }
  activePage = requestedPage;
  document.querySelectorAll('[data-page]').forEach((element) => {
    const active = element.dataset.page === activePage;
    element.hidden = !active;
    element.classList.toggle('is-active', active);
  });
  document.querySelectorAll('[data-nav]').forEach((element) => {
    const active = element.dataset.nav === activePage;
    element.classList.toggle('is-active', active);
    if (active) element.setAttribute('aria-current', 'page'); else element.removeAttribute('aria-current');
  });
  const [title, description] = PAGE_META[activePage];
  ui.pageTitle.textContent = title;
  ui.pageDescription.textContent = description;
  if (updateHash && location.hash !== `#${activePage}`) history.replaceState(null, '', `#${activePage}`);
  if (previousPage === 'controls' && activePage !== 'controls') leaveControlPage('controls_page_left');
  if (activePage === 'controls' && previousPage !== 'controls') enterControlPage();
  navigationLogFeature?.onPageChange(previousPage, activePage);
  if (activePage === 'sensors') datasetFeature?.activate();
  else datasetFeature?.deactivate();
  if (previousPage === 'sensors' && activePage !== 'sensors' && cameraRecording) {
    stopCameraRecording(cameraRecordingCleanupPolicy('sensors_page_left'));
  }
  syncPointcloudTransport();
  syncCameraTransport();
  requestAnimationFrame(() => {
    if (activePage === 'mapping') {
      scene3d?.resize();
      liveMap2d?.resize();
      redrawActiveMap();
    } else if (activePage === 'maps') {
      savedScene3d?.resize();
      redrawSavedMap();
      drawMapEditor();
    } else if (activePage === 'navigation') {
      navigationScene3d?.resize();
      updateNavigationModelPanel({ force: true });
      drawNavigationMap();
      refreshNavigationParameters();
      controlBridgeServiceFeature?.refresh();
      navigationLogFeature?.refresh(true);
    } else if (activePage === 'settings') {
      serviceLifecycleFeature?.refresh();
    }
  });
}

function showToast(message, error = false) {
  ui.toast.textContent = message;
  ui.toast.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { ui.toast.className = 'toast'; }, 2800);
}

function overviewTelemetryLive(health) {
  health = health || {};
  const targetConnected = health.robot_target_connected == null
    ? Boolean(health.robot_ip)
    : Boolean(health.robot_target_connected);
  return Boolean(health.agent_ready && targetConnected && health.robot_online);
}

function overviewUnavailableReason(health) {
  health = health || {};
  if (!health.agent_ready) return '에이전트 연결 끊김';
  const targetConnected = health.robot_target_connected == null
    ? Boolean(health.robot_ip)
    : Boolean(health.robot_target_connected);
  return targetConnected ? '로봇 오프라인' : '로봇 대상 연결 해제됨';
}

function renderOverviewUnavailable(reason, options) {
  const label = String(reason || '연결 확인 불가');
  const clearLive = options?.clearLive !== false;
  const transition = overviewTelemetryAvailability !== false;
  overviewTelemetryAvailability = false;
  ui.linkMetric.textContent = 'OFFLINE';
  ui.linkSub.textContent = label;
  ui.cameraMetric.textContent = 'OFFLINE';
  ui.cameraSub.textContent = label;
  ui.cameraSub.title = label;
  ui.lidarMetric.textContent = 'OFFLINE';
  ui.lidarSub.textContent = label;
  ui.lidarSub.title = label;
  ui.batteryMetric.textContent = 'OFFLINE';
  ui.batterySub.textContent = label;
  cameraStatusMeta = null;
  if (clearLive && transition) resetLiveRobotSessionView();
}

function invalidateStateRequests() {
  stateRequestGeneration += 1;
}

function updateHealth(health) {
  const ready = Boolean(health.agent_ready);
  const online = Boolean(health.robot_online);
  robotTargetConnected = health.robot_target_connected == null
    ? Boolean(health.robot_ip)
    : Boolean(health.robot_target_connected);
  const rosTransport = health.ros_transport || {};
  const rosInterfaceReady = rosTransport.interface_ready ?? health.ros_interface_ready;
  const offlineViewer = Boolean(rosTransport.offline_viewer ?? health.ros_offline_viewer);
  ui.connectionChip.className = `connection-chip ${ready && rosInterfaceReady === true && online ? 'ok' : ready ? 'waiting' : 'error'}`;
  ui.connectionLabel.textContent = !ready
    ? '에이전트 오류'
    : !robotTargetConnected
      ? '로봇 대상 연결 해제됨'
    : !online
      ? '로봇 오프라인'
    : offlineViewer || rosInterfaceReady === false
      ? 'ROS/DDS 오프라인 뷰어'
      : rosInterfaceReady === true
        ? 'ROS/DDS 인터페이스 준비'
        : 'ROS 에이전트 연결됨';
  ui.agentHost.textContent = health.hostname || '—';
  const rosInterface = rosTransport.interface ? ` · ${rosTransport.interface}` : '';
  ui.rosRuntime.textContent = `${health.ros_distro || '—'} · ${health.rmw || 'default'}${rosInterface}`;
  ui.rosDomain.textContent = health.ros_domain_id ?? '0';
  ui.topicCount.textContent = health.topic_count ?? '—';
  ui.profileLabel.textContent = (health.profile || 'GENERIC ROS 2').toUpperCase();
  const healthRobotType = window.RobotProfiles?.robotTypeId?.(health.robot_type || health.profile_id);
  const configurationCompatible = robotTargetConnected
    && !robotTypeDirty
    && !Boolean(health.restart_required || health.control_restart_required)
    && (!healthRobotType || healthRobotType === selectedRobotType);
  if (robotRuntimeDataCompatible && !configurationCompatible) resetLiveRobotSessionView();
  robotRuntimeDataCompatible = configurationCompatible && online;
  updateLiveModelBadge();
  if (!robotTypeDirty && healthRobotType && healthRobotType !== selectedRobotType && robotTypes.some((profile) => profile.id === healthRobotType)) {
    activateRobotType(healthRobotType);
  }
  if (!robotIpDirty && document.activeElement !== ui.robotIp) ui.robotIp.value = health.robot_ip || '';
  ui.connectedRobotTarget.textContent = robotTargetConnected
    ? `${health.robot_type || selectedRobotType || 'robot'} · ${health.robot_ip || 'IP 확인 중'}`
    : '연결 안 됨';
  ui.disconnectButton.disabled = robotConnectionBusy || !robotTargetConnected;
  ui.linkMetric.textContent = online ? (health.robot_latency_ms != null ? `${health.robot_latency_ms} ms` : 'ONLINE') : 'OFFLINE';
  ui.linkSub.textContent = health.robot_ip || 'IP not configured';
  if (health.last_error) console.warn('Robot Scope:', health.last_error);
}

function isLiveCloudReady() {
  const cloudState = latestState?.mapping?.cloud?.state;
  const mappingState = latestState?.mapping?.state;
  return cloudState === 'ok' || mappingState === 'mapping' || mappingState === 'cloud_only';
}

function liveSceneCloud(candidate = lastCloudSnapshot) {
  return candidate?.points?.length && isLiveCloudReady() ? candidate : null;
}

function savedSceneCloud() {
  return offlineCloudSnapshot?.points?.length ? offlineCloudSnapshot : null;
}

function cloudPointCount(cloud) {
  return Number(cloud?.sent_points || (cloud?.points?.length ? Math.floor(cloud.points.length / 3) : 0));
}

function cloudPointSummary(cloud) {
  const shown = cloudPointCount(cloud);
  const source = Math.max(shown, Number(cloud?.source_points || shown));
  return shown < source
    ? `${shown.toLocaleString()} / ${source.toLocaleString()}`
    : shown.toLocaleString();
}

function normalizePointLimit(value) {
  if (value == null || value === 'all') return null;
  const number = Math.floor(Number(value));
  if (!Number.isFinite(number) || number < 1000 || number > 1000000) {
    throw new Error('포인트 수는 1,000~1,000,000 사이여야 합니다.');
  }
  return number;
}

function pointBudgetCacheKey(mapId, limit = savedPointLimit, kind = 'pointcloud3d', revision = '') {
  const version = revision || 'legacy';
  if (kind === 'occupancy2d') return `${mapId}:${version}:grid`;
  return `${mapId}:${version}:${limit == null ? 'all' : limit}`;
}

function savedPointDataUrl(meta) {
  const base = meta.data_url || `/api/v1/saved-maps/${encodeURIComponent(meta.id)}/data`;
  const separator = base.includes('?') ? '&' : '?';
  return `${base}${separator}max_points=${savedPointLimit == null ? 'all' : encodeURIComponent(savedPointLimit)}`;
}

function storedPointLimit(key) {
  try {
    const value = localStorage.getItem(key);
    if (value == null) return undefined;
    return normalizePointLimit(value);
  } catch (_) {
    return undefined;
  }
}

function rememberPointLimit(key, value) {
  try { localStorage.setItem(key, value == null ? 'all' : String(value)); } catch (_) {}
}

function syncPointBudgetControl(select, wrapper, input, value) {
  const option = value == null ? 'all' : String(value);
  const known = Array.from(select.options).some((item) => item.value === option);
  select.value = known ? option : 'custom';
  wrapper.classList.toggle('is-hidden', select.value !== 'custom');
  if (value != null) input.value = String(value);
}

function updateSavedPointBudgetAvailability() {
  const disabled = savedPointBudgetBusy || selectedSavedMapMeta?.kind !== 'pointcloud3d';
  ui.savedPointBudget.disabled = disabled;
  ui.savedPointCustom.disabled = disabled;
  ui.savedPointApply.disabled = disabled;
  ui.savedPointCustomWrap.classList.toggle(
    'is-hidden',
    disabled || ui.savedPointBudget.value !== 'custom',
  );
}

async function applyLivePointLimit(value, notify = true) {
  if (livePointBudgetBusy) return;
  let limit;
  try {
    limit = normalizePointLimit(value);
  } catch (error) {
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
    return;
  }
  livePointBudgetBusy = true;
  ui.livePointBudget.disabled = ui.livePointCustom.disabled = ui.livePointApply.disabled = true;
  try {
    const settings = await api('/api/v1/pointcloud/settings', {
      method: 'POST',
      body: JSON.stringify({ max_points: limit }),
    });
    livePointLimit = settings.all_points ? null : Number(settings.max_points);
    rememberPointLimit('robotScope.livePointLimit', livePointLimit);
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    scene3d?.setPointLimit?.(livePointLimit);
    resetLiveCloudAccumulator();
    lastCloudSnapshot = null;
    pointcloudRequestGeneration += 1;
    cloudSeq = -1;
    sceneCloudDataKey = '';
    sceneCloudSourceKey = '';
    liveMap2dDataKey = '';
    liveMap2dSourceKey = '';
    await refreshPointcloud();
    if (notify) showToast(livePointLimit == null ? '실시간 점군을 ALL SESSION으로 표시합니다.' : `실시간 점군 표시량을 ${livePointLimit.toLocaleString()}점으로 설정했습니다.`);
  } catch (error) {
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
  } finally {
    livePointBudgetBusy = false;
    ui.livePointBudget.disabled = ui.livePointCustom.disabled = ui.livePointApply.disabled = false;
  }
}

async function applySavedPointLimit(value, notify = true) {
  if (savedPointBudgetBusy) return;
  let limit;
  try {
    limit = normalizePointLimit(value);
  } catch (error) {
    syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
    return;
  }
  const previousLimit = savedPointLimit;
  savedPointBudgetBusy = true;
  ui.savedPointBudget.disabled = ui.savedPointCustom.disabled = ui.savedPointApply.disabled = true;
  try {
    savedPointLimit = limit;
    syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
    savedScene3d?.setPointLimit?.(savedPointLimit);
    savedSceneCloudDataKey = '';
    savedSceneCloudSourceKey = '';
    if (selectedSavedMapMeta?.kind === 'pointcloud3d' && selectedSavedMapId !== '__fallback_cloud') {
      clearSavedMapCache(selectedSavedMapId);
      offlineCloudSnapshot = null;
      const loaded = await selectSavedMap(selectedSavedMapId, false, true);
      if (!loaded) throw new Error('선택한 포인트 수로 지도를 불러오지 못했습니다.');
    } else {
      redrawSavedMap();
    }
    rememberPointLimit('robotScope.savedPointLimit', savedPointLimit);
    if (notify) showToast(savedPointLimit == null ? '저장 지도의 모든 포인트를 표시합니다.' : `저장 지도 표시량을 ${savedPointLimit.toLocaleString()}점으로 설정했습니다.`);
  } catch (error) {
    savedPointLimit = previousLimit;
    savedScene3d?.setPointLimit?.(savedPointLimit);
    syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
    if (selectedSavedMapMeta?.kind === 'pointcloud3d' && selectedSavedMapId !== '__fallback_cloud') {
      await selectSavedMap(selectedSavedMapId, false);
    }
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
  } finally {
    savedPointBudgetBusy = false;
    updateSavedPointBudgetAvailability();
  }
}

async function initializePointBudgets() {
  const savedStored = storedPointLimit('robotScope.savedPointLimit');
  savedPointLimit = savedStored === undefined ? null : savedStored;
  syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
  savedScene3d?.setPointLimit?.(savedPointLimit);
  try {
    const settings = await api('/api/v1/pointcloud/settings');
    const stored = storedPointLimit('robotScope.livePointLimit');
    if (stored !== undefined && stored !== settings.max_points) {
      await applyLivePointLimit(stored, false);
      return;
    }
    livePointLimit = settings.all_points ? null : Number(settings.max_points);
  } catch (_) {}
  syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
  scene3d?.setPointLimit?.(livePointLimit);
}

function resetLiveCloudAccumulator() {
  liveCloudReservoir?.reset();
}

function resetLiveRobotSessionView() {
  resetLiveCloudAccumulator();
  lastCloudSnapshot = null;
  pointcloudRequestGeneration += 1;
  cloudSeq = -1;
  poseTrail = [];
  sceneCloudDataKey = '';
  sceneCloudSourceKey = '';
  liveMap2dDataKey = '';
  liveMap2dSourceKey = '';
  liveSceneHadCloud = false;
  clearLivePose();
  scene3d?.clearPointCloud();
  scene3d?.clearTrail();
  scene3d?.setRobotPose(null);
  liveMap2d?.clearPointCloud();
  liveMap2d?.setTrail([]);
  liveMap2d?.setPose(null);
  navigationScene3d?.resetRobotJointPositions?.();
  navigationScene3d?.setRobotPose(null);
  navigationModelPanelKey = '';
  updateNavigationModelPanel();
}

function accumulateRegisteredCloud(cloud) {
  if (cloud?.topic !== '/cloud_registered' || !cloud?.points?.length) {
    resetLiveCloudAccumulator();
    return cloud;
  }
  return liveCloudReservoir?.ingest(cloud, livePointLimit) || cloud;
}

function buildDemoPointcloud() {
  const points = [];
  const add = (x, y, z) => points.push(Number(x.toFixed(3)), Number(y.toFixed(3)), Number(z.toFixed(3)));
  for (let x = -6; x <= 6; x += .28) {
    for (let y = -4; y <= 4; y += .28) {
      if ((Math.round((x + y) * 100) % 5) === 0) add(x, y, 0);
    }
  }
  for (let z = 0; z <= 2.5; z += .16) {
    for (let x = -6; x <= 6; x += .22) {
      add(x, -4, z);
      if (x < -1.2 || x > 1.2 || z > 2.1) add(x, 4, z);
    }
    for (let y = -4; y <= 4; y += .22) {
      add(-6, y, z);
      add(6, y, z);
    }
  }
  for (let angle = 0; angle < Math.PI * 2; angle += .08) {
    for (let z = 0; z <= 1.1; z += .12) add(2.2 + Math.cos(angle) * .7, -.8 + Math.sin(angle) * .7, z);
  }
  return {
    seq: 'demo-1', topic: '/demo/pointcloud', frame_id: 'map', units: 'm',
    source_points: Math.floor(points.length / 3), sent_points: Math.floor(points.length / 3),
    bounds: { min: [-6, -4, 0], max: [6, 4, 2.5] },
    offline_snapshot: true, demo_snapshot: true, points,
  };
}

function updateOverview(state) {
  updateHealth(state.health);
  if (!overviewTelemetryLive(state.health)) {
    renderOverviewUnavailable(overviewUnavailableReason(state.health));
    updateSensors(state.sensors || []);
    updateSavedMapOverview();
    ui.lastUpdated.textContent = `Last update ${new Date().toLocaleTimeString('ko-KR', { hour12: false })} · OFFLINE`;
    syncPointcloudTransport();
    return;
  }
  overviewTelemetryAvailability = true;
  applyJointSnapshot(state.robot_joints);
  const camera = state.camera || {};
  const cloud = state.cloud || {};
  const grid = state.map || {};
  const mapping = state.mapping || {};
  const cameraSource = state.sources?.camera || '';
  const cloudSource = state.sources?.pointcloud || '';
  const odomSource = state.sources?.odometry || '';
  const gridSource = state.sources?.occupancy_grid || '';

  const directCamera = camera.direct_camera || {};
  const cameraTopicName = camera.topic || cameraSource;
  const cameraTopic = latestTopics.find((topic) => topic.name === cameraTopicName);
  const cameraSourceKey = cameraTopicName || camera.source || directCamera.uri || '';
  if (cameraSourceKey && !cameraCatalog.length) noteCameraSource(cameraSourceKey);
  // /api/v1/state is also the liveness clock for the direct Go2 multicast
  // camera.  Merge it into the latest WS frame metadata so a frozen canvas
  // becomes stale even when no more WebSocket messages arrive.
  if (!cameraCatalog.length) cameraStatusMeta = { ...camera };
  const cameraLabel = camera.source_label || camera.topic || cameraSource || 'NO SOURCE';
  const cameraTransport = camera.transport || directCamera.transport || '';
  const cameraInterface = camera.interface || directCamera.interface || '';
  const cameraFps = camera.fps ?? directCamera.fps ?? cameraTopic?.hz;
  const cameraAge = camera.age_s ?? directCamera.age_s ?? cameraTopic?.age_s;
  const reportedCameraState = camera.state || directCamera.state || cameraTopic?.state || 'waiting';
  const cameraOnDemand = Boolean(directCamera.configured && reportedCameraState === 'stopped' && activePage !== 'sensors');
  const reportedCameraLive = camera.live ?? directCamera.live ?? (reportedCameraState === 'ok');
  const cameraLive = Boolean(reportedCameraLive) && (cameraAge == null || Number(cameraAge) <= 3);
  ui.cameraMetric.textContent = cameraLive ? formatHz(cameraFps) : cameraOnDemand ? 'ON DEMAND' : 'OFFLINE';
  ui.cameraSub.textContent = [cameraLabel, cameraTransport, cameraInterface].filter(Boolean).join(' · ') || 'No camera source';
  ui.cameraSub.title = ui.cameraSub.textContent;
  ui.cameraTopicLabel.textContent = cameraLabel;
  ui.cameraTopicLabel.title = camera.topic || cameraSource || cameraLabel;
  const cameraWidth = camera.width || directCamera.width || '';
  const cameraHeight = camera.height || directCamera.height || '';
  const cameraFormat = camera.format && camera.format !== 'none' ? camera.format.toUpperCase() : '';
  const cameraDimensions = cameraWidth && cameraHeight ? `${cameraWidth}×${cameraHeight}` : '';
  ui.cameraCodecLabel.textContent = [cameraFormat, cameraDimensions, cameraTransport].filter(Boolean).join(' · ') || '—';
  setStatePill(
    ui.cameraState,
    cameraLive ? 'ok' : cameraOnDemand ? 'waiting' : reportedCameraState,
    cameraLive ? 'LIVE' : cameraOnDemand ? 'ON DEMAND' : String(reportedCameraState).toUpperCase(),
  );
  if (cameraCatalog.length) {
    const primarySlot = primaryCameraSlot();
    const selectedCamera = cameraSourceForId(cameraPrimarySourceId) || {};
    primarySlot.statusMeta = selectedCamera;
    const selectedMetadata = { ...selectedCamera };
    cameraStatusMeta = { ...selectedMetadata };
    const selectedLabel = selectedCamera.label || selectedCamera.id || 'NO SOURCE';
    const selectedAge = Number(selectedMetadata.age_s);
    const selectedState = String(selectedMetadata.state || '').toLowerCase();
    const selectedLive = selectedMetadata.live === true
      && (!selectedState || ['ok', 'live'].includes(selectedState))
      && (selectedMetadata.age_s == null || (Number.isFinite(selectedAge) && selectedAge <= 3));
    const selectedOnDemand = selectedState === 'stopped' && activePage !== 'sensors';
    ui.cameraMetric.textContent = selectedLive
      ? formatHz(selectedMetadata.fps)
      : selectedOnDemand ? 'ON DEMAND' : 'OFFLINE';
    ui.cameraSub.textContent = [selectedLabel, selectedMetadata.transport, selectedCamera.id].filter(Boolean).join(' · ');
    ui.cameraSub.title = ui.cameraSub.textContent;
    renderCameraSlotIdentity(primarySlot);
  }
  syncCameraFrameFreshness();

  const cloudMetric = mapping.cloud || {};
  const liveCloud = liveSceneCloud();
  const cloudTopic = latestTopics.find((topic) => topic.name === cloudSource);
  const odomTopic = latestTopics.find((topic) => topic.name === odomSource);
  const gridTopic = latestTopics.find((topic) => topic.name === gridSource);
  const cloudFrame = cloud.frame_id || liveCloud?.frame_id || '';
  const poseFrame = state.robot_pose?.frame_id || '';
  const frameMismatch = Boolean(cloudFrame && poseFrame && cloudFrame !== poseFrame);

  ui.lidarMetric.textContent = liveCloud ? formatHz(cloudMetric.hz ?? cloudTopic?.hz) : 'OFFLINE';
  ui.liveCloudTopic.textContent = cloudSource || 'NO SOURCE';
  ui.liveCloudStatus.textContent = liveCloud ? `live · ${formatHz(cloudMetric.hz ?? cloudTopic?.hz)} · ${cloudFrame || 'no frame'}` : (cloudTopic?.state || 'waiting');
  ui.liveOdomTopic.textContent = odomSource || 'NO SOURCE';
  ui.liveOdomStatus.textContent = odomTopic?.state === 'ok' ? `live · ${formatHz(odomTopic.hz)}` : (odomTopic?.state || 'waiting');
  ui.liveMapTopic.textContent = gridSource || 'NO SOURCE';
  ui.liveMapStatus.textContent = gridTopic?.state === 'ok' ? (gridTopic.hz == null ? 'static ready' : `live · ${formatHz(gridTopic.hz)}`) : (gridTopic?.state || 'waiting');

  const liveView = desiredMapView();
  if (liveView === 'occupancy') {
    ui.mapFrame.textContent = `FRAME ${grid.frame_id || '—'}`;
    ui.mapPoints.textContent = grid.width && grid.height ? `${grid.width}×${grid.height} CELLS` : '0 CELLS';
    setStatePill(ui.mappingState, gridTopic?.state || 'waiting', gridTopic?.state === 'ok' && state.health?.robot_online ? 'LIVE 2D MAP' : 'LIVE DATA WAITING');
  } else {
    ui.mapFrame.textContent = `FRAME ${cloud.frame_id || liveCloud?.frame_id || '—'}`;
    const displayPoints = liveCloud?.accumulated_registered_scans ? cloudPointCount(liveCloud) : Number(cloud.sent_points || cloudPointCount(liveCloud));
    const pointLabel = liveCloud ? cloudPointSummary(liveCloud) : displayPoints.toLocaleString();
    const projectionCells = liveView === 'projection' ? Number(liveMap2d?.snapshot?.().cellCount || 0) : 0;
    ui.mapPoints.textContent = `${pointLabel} POINTS${projectionCells ? ` · ${projectionCells.toLocaleString()} CELLS` : ''}${liveCloud?.accumulated_registered_scans ? ' · ACCUMULATED' : ''}`;
    const mappingLabels = { mapping: 'WORLD FRAME · LIVE', cloud_only: 'CLOUD LIVE', waiting: 'LIVE DATA WAITING', stale: 'LIVE DATA STALE' };
    const label = liveView === 'projection'
      ? (frameMismatch ? '2D PROJECTION · SENSOR FRAME' : 'LIVE 2D · POINT PROJECTION')
      : frameMismatch ? 'SENSOR FRAME · EXTRINSIC' : (mappingLabels[mapping.state] || 'CLOUD LIVE');
    setStatePill(ui.mappingState, liveCloud ? (frameMismatch ? 'waiting' : (mapping.state || 'cloud_only')) : 'waiting', liveCloud ? label : 'LIVE DATA WAITING');
  }
  renderLidarSourceIdentity();

  const battery = (state.sensors || []).find((sensor) => sensor.values?.battery_soc != null || sensor.category === 'battery');
  const batteryAge = Number(battery?.age_s);
  const batteryFresh = battery?.state === 'ok'
    && (battery?.age_s == null || (Number.isFinite(batteryAge) && batteryAge >= 0));
  const soc = battery?.values?.battery_soc ?? (battery?.values?.percentage != null ? battery.values.percentage * 100 : null);
  ui.batteryMetric.textContent = batteryFresh && soc != null ? `${Math.round(soc)}%` : '—';
  ui.batterySub.textContent = batteryFresh
    ? `${safeNumber(battery.values.power_v ?? battery.values.voltage, 1)} V · ${formatHz(battery.hz)}`
    : battery ? '배터리 데이터 STALE' : '데이터 대기 중';

  updateSensors(state.sensors || []);
  updateOdometry(state.sensors || [], odomSource);
  updateSavedMapOverview();
  ui.lastUpdated.textContent = `Last update ${new Date().toLocaleTimeString('ko-KR', { hour12: false })}`;
  // AUTO may switch between a real OccupancyGrid and point projection as ROS
  // sources appear or disappear.  Keep the binary cloud transport aligned
  // with that decision without waiting for a page navigation event.
  syncPointcloudTransport();
}

function formatBounds(bounds) {
  if (!bounds?.min || !bounds?.max) return '—';
  const span = bounds.min.map((value, index) => Math.abs(Number(bounds.max[index]) - Number(value)));
  return span.every(Number.isFinite) ? `${span.map((value) => value.toFixed(1)).join(' × ')} m` : '—';
}

function updateSavedMapOverview() {
  const cloud = savedSceneCloud();
  const entries = savedMapCatalog.length ? savedMapCatalog : (cloud ? [{
    id: '__fallback_cloud', name: cloud.demo_snapshot ? 'Public demo cloud' : 'Saved point cloud',
    kind: 'pointcloud3d', file_name: cloud.topic || '/saved/map', point_count: cloudPointCount(cloud),
    frame_id: cloud.frame_id || 'map', bounds: cloud.bounds,
  }] : []);
  if (!selectedSavedMapMeta && entries.length) {
    selectedSavedMapMeta = entries[0];
    selectedSavedMapId = entries[0].id;
  }
  ui.savedMapCount.textContent = `${entries.length} map${entries.length === 1 ? '' : 's'}`;
  ui.savedMapList.innerHTML = entries.length ? entries.map((entry) => {
    const grid = entry.kind === 'occupancy2d';
    const count = grid ? `${entry.width || '—'}×${entry.height || '—'}` : `${Number(entry.point_count || 0).toLocaleString()} pts`;
    const fileLabel = entry.file_name || (grid ? '2D occupancy' : '3D point cloud');
    const editorLabel = grid && (!entry.manageable || entry.editable !== true) ? `${fileLabel} · 편집 불가` : fileLabel;
    return `<button class="saved-map-item${selectedSavedMapId === entry.id ? ' is-active' : ''}" type="button" data-saved-map-id="${escapeHtml(entry.id)}"><i>${grid ? '▦' : '◌'}</i><span><strong>${escapeHtml(entry.name || 'Saved map')}</strong><small>${escapeHtml(editorLabel)}</small></span><b>${escapeHtml(count)}</b></button>`;
  }).join('') : '<div class="sensor-placeholder">저장 지도가 없습니다.</div>';

  const showingGrid = selectedSavedMapMeta?.kind === 'occupancy2d';
  const selected = showingGrid ? savedOccupancySnapshot : cloud;
  if (showingGrid && selected) {
    ui.savedMapTitle.textContent = selectedSavedMapMeta?.name || selected.name || 'Saved 2D map';
    ui.savedMapSource.textContent = selectedSavedMapMeta?.file_name || selected.topic || '/saved/map';
    ui.savedMapDetailFrame.textContent = selected.frame_id || '—';
    ui.savedMapDetailPoints.textContent = `${selected.width}×${selected.height} cells`;
    ui.savedMapBounds.textContent = `${safeNumber(selected.width * selected.resolution, 1)} × ${safeNumber(selected.height * selected.resolution, 1)} m`;
    ui.savedMapFrame.textContent = `FRAME ${selected.frame_id || '—'}`;
    ui.savedMapPoints.textContent = `${selected.width}×${selected.height} CELLS`;
    setStatePill(ui.savedMappingState, 'saved', 'SAVED 2D MAP');
  } else if (!showingGrid && selected) {
    const demo = Boolean(selected.demo_snapshot);
    ui.savedMapTitle.textContent = selectedSavedMapMeta?.name || (demo ? 'Public demo cloud' : selected.name || 'Saved point cloud');
    ui.savedMapSource.textContent = selectedSavedMapMeta?.file_name || selected.topic || '/saved/map';
    ui.savedMapDetailFrame.textContent = selected.frame_id || '—';
    ui.savedMapDetailPoints.textContent = `${cloudPointSummary(selected)} points`;
    ui.savedMapBounds.textContent = formatBounds(selected.bounds);
    ui.savedMapFrame.textContent = `FRAME ${selected.frame_id || '—'}`;
    ui.savedMapPoints.textContent = `${cloudPointSummary(selected)} POINTS · ${demo ? 'DEMO' : 'SAVED'}`;
    setStatePill(ui.savedMappingState, 'saved', demo ? 'DEMO 3D MAP' : 'SAVED 3D MAP');
  } else {
    ui.savedMapTitle.textContent = selectedSavedMapMeta?.name || '—';
    ui.savedMapSource.textContent = selectedSavedMapMeta?.file_name || '—';
    ui.savedMapDetailFrame.textContent = selectedSavedMapMeta?.frame_id || '—';
    ui.savedMapDetailPoints.textContent = showingGrid ? '2D map loading…' : '3D map loading…';
    ui.savedMapBounds.textContent = '—';
    setStatePill(ui.savedMappingState, entries.length ? 'waiting' : 'waiting', entries.length ? 'LOADING MAP' : 'NO SAVED MAP');
  }
  updateSavedPointBudgetAvailability();
  updateSavedMapManagement();
  syncMapConversionPanel();
}

function updateSavedMapManagement() {
  const manageable = Boolean(selectedSavedMapMeta?.manageable && selectedSavedMapId !== '__fallback_cloud');
  const editorDirty = Boolean(mapEditorSession?.changedCount);
  const operationBusy = Boolean(mapConversionPending || mapConversionCompleting || mapEditorBusy);
  const enabled = manageable && !savedMapMutationBusy && !editorDirty && !operationBusy;
  if (document.activeElement !== ui.savedMapNameInput) {
    ui.savedMapNameInput.value = selectedSavedMapMeta?.name || '';
  }
  ui.savedMapNameInput.disabled = !enabled;
  ui.savedMapRenameButton.disabled = !enabled;
  ui.savedMapDeleteButton.disabled = !enabled;
  const listBusy = savedMapMutationBusy || mapEditorBusy || Boolean(mapConversionPending || mapConversionCompleting);
  ui.savedMapList.setAttribute('aria-busy', listBusy ? 'true' : 'false');
  ui.savedMapList.querySelectorAll('button').forEach((button) => {
    button.disabled = listBusy;
  });
  if (editorDirty) ui.savedMapManageNote.textContent = '편집 중에는 이름 변경·삭제가 잠깁니다. 복사본 저장 또는 RESET 후 진행하세요.';
  else if (operationBusy) ui.savedMapManageNote.textContent = '지도 작업이 끝난 뒤 이름 변경·삭제할 수 있습니다.';
  else if (!selectedSavedMapMeta) ui.savedMapManageNote.textContent = '관리할 지도를 선택하세요.';
  else if (!manageable) ui.savedMapManageNote.textContent = '번들 데모 또는 읽기 전용 지도는 변경할 수 없습니다.';
  else if (selectedSavedMapMeta.kind === 'occupancy2d') ui.savedMapManageNote.textContent = '이름 변경·삭제 시 YAML과 연결된 PGM을 함께 처리합니다.';
  else ui.savedMapManageNote.textContent = '선택한 저장 지도 파일의 이름을 변경하거나 삭제합니다.';
}

function validSavedMapName(value) {
  return /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(String(value || ''));
}

function suggestedDerivedMapName(source, suffix) {
  const base = String(source?.name || source?.file_name || 'map').replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]+/g, '_');
  const normalized = /^[A-Za-z0-9]/.test(base) ? base : `map_${base}`;
  return `${normalized.slice(0, Math.max(1, 64 - suffix.length))}${suffix}`;
}

function conversionCloudMaps() {
  return savedMapCatalog.filter((entry) => entry.kind === 'pointcloud3d' && entry.manageable && entry.format === 'pcd-binary');
}

function renderMapConversionFeedback(kind, label, message, progress = 0) {
  setStatePill(ui.mapConvertState, kind, label);
  ui.mapConvertMessage.textContent = message;
  ui.mapConvertMessage.classList.toggle('is-error', kind === 'error');
  ui.mapConvertProgress.value = Math.max(0, Math.min(1, Number(progress) || 0));
  ui.mapConvertProgressLabel.textContent = `${Math.round(ui.mapConvertProgress.value * 100)}%`;
}

function setMapConversionFeedback(kind, label, message, progress = 0) {
  mapConversionFeedback = { kind, label, message, progress };
  renderMapConversionFeedback(kind, label, message, progress);
}

function syncMapConversionPanel() {
  const clouds = conversionCloudMaps();
  const fingerprint = clouds.map((entry) => `${entry.id}\u0000${entry.name}`).join('\u0001');
  if (fingerprint !== mapConversionSourceFingerprint) {
    const previous = ui.mapConvertSource.value;
    mapConversionSourceFingerprint = fingerprint;
    ui.mapConvertSource.innerHTML = clouds.length
      ? clouds.map((entry) => `<option value="${escapeHtml(entry.id)}">${escapeHtml(entry.name || entry.file_name || 'Saved PCD')}</option>`).join('')
      : '<option value="">저장된 PCD 없음</option>';
    const selectedCloud = selectedSavedMapMeta?.kind === 'pointcloud3d' ? selectedSavedMapId : '';
    ui.mapConvertSource.value = clouds.some((entry) => entry.id === previous)
      ? previous
      : clouds.some((entry) => entry.id === selectedCloud) ? selectedCloud : clouds[0]?.id || '';
  }
  const source = clouds.find((entry) => entry.id === ui.mapConvertSource.value);
  if (!mapConversionNameDirty && document.activeElement !== ui.mapConvertName) {
    ui.mapConvertName.value = source ? suggestedDerivedMapName(source, '_2d') : '';
  }
  const busy = Boolean(mapConversionPending || mapConversionCompleting);
  const editorDirty = Boolean(mapEditorSession?.changedCount);
  const controls = [ui.mapConvertSource, ui.mapConvertName, ui.mapConvertZMin, ui.mapConvertZMax, ui.mapConvertResolution, ui.mapConvertRadius, ui.mapConvertNeighbors, ui.mapConvertBackground];
  controls.forEach((control) => { control.disabled = busy; });
  ui.mapConvertStart.disabled = busy || !source || editorDirty || !validSavedMapName(ui.mapConvertName.value.trim());
  if (busy) return;
  if (mapConversionFeedback) {
    renderMapConversionFeedback(mapConversionFeedback.kind, mapConversionFeedback.label, mapConversionFeedback.message, mapConversionFeedback.progress);
  } else if (!source) {
    renderMapConversionFeedback('waiting', 'NO PCD', '변환할 저장 PCD가 없습니다.', 0);
  } else if (editorDirty) {
    renderMapConversionFeedback('waiting', 'EDIT UNSAVED', '2D 편집 내용을 복사본으로 저장하거나 RESET한 뒤 변환하세요.', 0);
  } else if (ui.mapConvertBackground.value === 'free') {
    renderMapConversionFeedback(
      'waiting',
      'FREE BOUNDS',
      '주의: FREE는 PCD 경계 사각형의 미관측 영역까지 자유공간으로 처리합니다 (legacy/PDF 호환).',
      0,
    );
  } else {
    renderMapConversionFeedback('waiting', 'IDLE', '높이 슬라이스와 노이즈 필터를 적용해 PGM·YAML 복사본을 생성합니다.', 0);
  }
}

function conversionNumber(input, label, minimum, maximum) {
  const raw = String(input.value || '').trim();
  const value = Number(raw);
  if (!raw || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${label} 값은 ${minimum}~${maximum} 범위여야 합니다.`);
  }
  return value;
}

async function startSavedMapConversion() {
  if (mapConversionPending || mapConversionCompleting || mapEditorSession?.changedCount) return;
  const source = conversionCloudMaps().find((entry) => entry.id === ui.mapConvertSource.value);
  if (!source) { showToast('변환할 저장 PCD를 선택하세요.', true); return; }
  const name = ui.mapConvertName.value.trim();
  if (!validSavedMapName(name)) { showToast('출력 이름은 영문·숫자로 시작하고 영문·숫자·_·-만 사용할 수 있습니다.', true); return; }
  try {
    const zMin = conversionNumber(ui.mapConvertZMin, 'thre_z_min', -20, 20);
    const zMax = conversionNumber(ui.mapConvertZMax, 'thre_z_max', -20, 20);
    const resolution = conversionNumber(ui.mapConvertResolution, 'resolution', 0.01, 1);
    const noiseRadius = conversionNumber(ui.mapConvertRadius, 'radius', 0.01, 2);
    const minNeighbors = conversionNumber(ui.mapConvertNeighbors, 'min neighbors', 1, 1000);
    const background = ui.mapConvertBackground.value === 'free' ? 'free' : 'unknown';
    if (zMin >= zMax) throw new Error('thre_z_min은 thre_z_max보다 작아야 합니다.');
    if (!Number.isInteger(minNeighbors)) throw new Error('min neighbors는 정수여야 합니다.');
    mapConversionFeedback = null;
    const pending = { sourceId: source.id, name, jobId: '', trackingStartedAt: 0 };
    mapConversionPending = pending;
    setStatePill(ui.mapConvertState, 'waiting', 'STARTING');
    ui.mapConvertProgress.removeAttribute('value');
    ui.mapConvertProgressLabel.textContent = 'START';
    ui.mapConvertMessage.classList.remove('is-error');
    ui.mapConvertMessage.textContent = `${source.name || source.file_name} 변환 작업을 시작하고 있습니다.`;
    syncMapConversionPanel();
    syncMapEditorUi();
    const response = await api(`/api/v1/saved-maps/${encodeURIComponent(source.id)}/convert-2d`, {
      method: 'POST',
      body: JSON.stringify({
        name,
        z_min: zMin,
        z_max: zMax,
        resolution,
        noise_radius: noiseRadius,
        min_neighbors: minNeighbors,
        background,
      }),
    });
    const operation = response.operation || response;
    const operationJobId = String(operation?.job_id || '').trim();
    const responseJobId = String(response?.job_id || '').trim();
    if (operationJobId && responseJobId && operationJobId !== responseJobId) {
      throw new Error('서버 변환 작업 job_id가 서로 일치하지 않습니다.');
    }
    const jobId = operationJobId || responseJobId;
    if (!/^[0-9a-f]{32}$/.test(jobId)) throw new Error('서버가 유효한 변환 작업 job_id를 반환하지 않았습니다. 백엔드 버전을 확인하세요.');
    pending.jobId = jobId;
    pending.trackingStartedAt = Date.now();
    mappingControlRequestGeneration += 1;
    renderMapConversionOperation({ ...operation, job_id: jobId });
    await refreshMappingControl();
  } catch (error) {
    mapConversionPending = null;
    setMapConversionFeedback('error', 'START FAILED', `2D 변환 시작 실패: ${error.message}`, 0);
    syncMapEditorUi();
  }
}

function mapConversionMatches(operation) {
  if (!mapConversionPending?.jobId || !operation?.job_id) return false;
  return String(operation.job_id) === mapConversionPending.jobId;
}

function normalizedOperationProgress(operation) {
  const raw = Number(operation.progress ?? operation.progress_ratio ?? operation.progress_percent);
  if (!Number.isFinite(raw)) return null;
  return Math.max(0, Math.min(1, raw > 1 ? raw / 100 : raw));
}

function mapConversionTrackingExpired() {
  const startedAt = Number(mapConversionPending?.trackingStartedAt);
  return Boolean(
    mapConversionPending?.jobId &&
    Number.isFinite(startedAt) &&
    startedAt > 0 &&
    Date.now() - startedAt >= MAP_CONVERSION_TRACKING_TIMEOUT_MS
  );
}

function failMapConversionTracking(message) {
  if (!mapConversionPending) return;
  mapConversionPending = null;
  setMapConversionFeedback('error', 'TRACKING LOST', message, 0);
  syncMapEditorUi();
}

function renderMapConversionOperation(operation) {
  if (!mapConversionPending?.jobId || mapConversionCompleting) return;
  if (!mapConversionMatches(operation)) {
    failMapConversionTracking('서버 작업 snapshot이 기대한 job_id와 다르거나 idle로 변경됐습니다. 변환 추적을 중단했으므로 매핑 로그에서 실제 결과를 확인하세요.');
    return;
  }
  const state = String(operation.state || '').toLowerCase();
  if (['succeeded', 'failed'].includes(state)) {
    if (operation.job_id) handledMappingOperation = `${operation.job_id}:${state}`;
    if (state === 'succeeded') completeSavedMapConversion(operation);
    else {
      mapConversionPending = null;
      setMapConversionFeedback('error', 'CONVERT FAILED', operation.error || 'PCD 2D 변환에 실패했습니다.', 0);
      syncMapEditorUi();
    }
    return;
  }
  if (mapConversionTrackingExpired()) {
    failMapConversionTracking('15분 동안 변환 완료를 확인하지 못해 추적을 중단했습니다. 서버 작업은 계속될 수 있으므로 매핑 로그와 Saved Maps를 확인하세요.');
    return;
  }
  const progress = normalizedOperationProgress(operation);
  setStatePill(ui.mapConvertState, 'waiting', state ? state.toUpperCase() : 'WORKING');
  if (progress == null) {
    ui.mapConvertProgress.removeAttribute('value');
    ui.mapConvertProgressLabel.textContent = 'WORKING';
  } else {
    ui.mapConvertProgress.value = progress;
    ui.mapConvertProgressLabel.textContent = `${Math.round(progress * 100)}%`;
  }
  ui.mapConvertMessage.classList.remove('is-error');
  ui.mapConvertMessage.textContent = operation.message || `${mapConversionPending.name} PGM·YAML을 생성하고 검증하고 있습니다.`;
}

async function completeSavedMapConversion(operation) {
  if (mapConversionCompleting || !mapConversionPending) return;
  mapConversionCompleting = true;
  setStatePill(ui.mapConvertState, 'waiting', 'INDEXING');
  ui.mapConvertProgress.value = 1;
  ui.mapConvertProgressLabel.textContent = '100%';
  ui.mapConvertMessage.textContent = '변환 결과를 Saved Maps 목록에 반영하고 있습니다.';
  try {
    await refreshSavedMaps();
    const resultId = String(
      operation.details?.result_map_id || operation.result_map_id || operation.map_id || '',
    );
    const result = savedMapCatalog.find((entry) => entry.id === resultId);
    if (!result) throw new Error('완료된 2D 지도를 목록에서 찾지 못했습니다. 새로고침 후 확인하세요.');
    mapConversionPending = null;
    const loaded = await selectSavedMap(result.id, false, true);
    if (!loaded) throw new Error('변환 지도는 생성됐지만 대시보드에서 선택하지 못했습니다.');
    mapConversionNameDirty = false;
    setMapConversionFeedback('ok', 'CONVERTED', `${result.name} 2D 지도를 생성하고 선택했습니다.`, 1);
    showToast(`${result.name} 2D 지도를 생성했습니다.`);
  } catch (error) {
    mapConversionPending = null;
    setMapConversionFeedback('error', 'RESULT FAILED', error.message, 0);
  } finally {
    mapConversionCompleting = false;
    syncMapEditorUi();
  }
}

function mapEditorRevision(snapshot) {
  return typeof snapshot?.revision === 'string' && /^[0-9a-f]{64}$/.test(snapshot.revision)
    ? snapshot.revision
    : null;
}

function mapEditorColor(value) {
  if (value === 100) return [7, 10, 9];
  if (value === 0) return [242, 246, 244];
  return [126, 137, 133];
}

function buildMapEditorSourceCanvas(session) {
  const canvas = document.createElement('canvas');
  canvas.width = session.width;
  canvas.height = session.height;
  const context = canvas.getContext('2d');
  const image = context.createImageData(session.width, session.height);
  for (let index = 0; index < session.cells.length; index += 1) {
    const x = index % session.width;
    const y = Math.floor(index / session.width);
    const output = ((session.height - 1 - y) * session.width + x) * 4;
    const color = mapEditorColor(session.cells[index]);
    image.data[output] = color[0];
    image.data[output + 1] = color[1];
    image.data[output + 2] = color[2];
    image.data[output + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  session.sourceCanvas = canvas;
  session.sourceContext = context;
}

function updateMapEditorSourcePixels(changes) {
  const session = mapEditorSession;
  if (!session?.sourceContext) return;
  for (const change of changes) {
    const x = change.index % session.width;
    const y = Math.floor(change.index / session.width);
    const color = mapEditorColor(session.cells[change.index]);
    session.sourceContext.fillStyle = `rgb(${color.join(',')})`;
    session.sourceContext.fillRect(x, session.height - 1 - y, 1, 1);
  }
}

function drawMapEditor() {
  mapEditorRenderFrame = 0;
  const canvas = ui.mapEditorCanvas;
  const { width, height } = resizeCanvas(canvas);
  const context = canvas.getContext('2d');
  context.fillStyle = '#06100e';
  context.fillRect(0, 0, width, height);
  const session = mapEditorSession;
  if (!session?.sourceCanvas) return;
  const scale = Math.min(width / session.width, height / session.height) * .94;
  const drawWidth = session.width * scale;
  const drawHeight = session.height * scale;
  const left = (width - drawWidth) / 2;
  const top = (height - drawHeight) / 2;
  context.imageSmoothingEnabled = false;
  context.drawImage(session.sourceCanvas, left, top, drawWidth, drawHeight);
  context.strokeStyle = 'rgba(93,222,216,.48)';
  context.lineWidth = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
  context.strokeRect(left, top, drawWidth, drawHeight);
  session.layout = { left, top, drawWidth, drawHeight, scale, canvasWidth: width, canvasHeight: height };
}

function scheduleMapEditorDraw() {
  if (mapEditorRenderFrame) return;
  mapEditorRenderFrame = requestAnimationFrame(drawMapEditor);
}

function setMapEditorFeedback(message, error = false) {
  mapEditorFeedback = { message, error };
  ui.mapEditorMessage.textContent = message;
  ui.mapEditorMessage.classList.toggle('is-error', error);
}

function syncMapEditorUi() {
  const session = mapEditorSession;
  const available = Boolean(session);
  const locked = mapEditorBusy || Boolean(mapConversionPending || mapConversionCompleting);
  const interactive = available && !locked;
  ui.mapEditorEmpty.hidden = available;
  if (!available) ui.mapEditorEmpty.textContent = mapEditorUnavailableReason;
  ui.mapEditorCanvas.classList.toggle('is-erasing', mapEditorTool === 'eraser');
  document.querySelectorAll('[data-map-editor-tool]').forEach((button) => {
    const active = button.dataset.mapEditorTool === mapEditorTool;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
    button.disabled = !interactive;
  });
  document.querySelectorAll('[data-map-editor-value]').forEach((button) => {
    const active = Number(button.dataset.mapEditorValue) === mapEditorCellValue;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
    button.disabled = !interactive || mapEditorTool === 'eraser';
  });
  ui.mapEditorBrushSize.disabled = !interactive;
  ui.mapEditorUndo.disabled = !interactive || !session?.undo.length;
  ui.mapEditorRedo.disabled = !interactive || !session?.redo.length;
  ui.mapEditorReset.disabled = !interactive || !session?.changedCount;
  ui.mapEditorSaveName.disabled = !interactive;
  ui.mapEditorSave.disabled = !interactive || !session?.changedCount || session?.sourceStale || !validSavedMapName(ui.mapEditorSaveName.value.trim());
  ui.mapEditorSource.textContent = available ? `SOURCE ${session.sourceName}` : 'SOURCE —';
  ui.mapEditorStats.textContent = available
    ? `변경 ${session.changedCount.toLocaleString()} cells · ${session.width}×${session.height}`
    : '변경 0 cells';
  ui.mapEditorBrushOutput.textContent = `${ui.mapEditorBrushSize.value} cells`;
  if (mapEditorBusy) setStatePill(ui.mapEditorState, 'waiting', 'SAVING COPY');
  else if (session?.sourceStale) setStatePill(ui.mapEditorState, 'error', 'SOURCE CHANGED');
  else if (available && session.changedCount) setStatePill(ui.mapEditorState, 'waiting', 'EDITING');
  else if (available) setStatePill(ui.mapEditorState, 'ok', 'READY');
  else setStatePill(ui.mapEditorState, 'waiting', 'NO MAP');
  if (!mapEditorFeedback) {
    ui.mapEditorMessage.classList.remove('is-error');
    ui.mapEditorMessage.textContent = available
      ? '검정=장애물, 흰색=빈 공간, 회색=미확인입니다. ERASER는 원본 셀 값을 복원합니다.'
      : mapEditorUnavailableReason;
  }
  updateSavedMapManagement();
  syncMapConversionPanel();
}

function detachMapEditor(reason = '편집할 저장 2D 지도를 선택하세요.') {
  mapEditorSession = null;
  mapEditorFeedback = null;
  mapEditorUnavailableReason = reason;
  if (mapEditorRenderFrame) cancelAnimationFrame(mapEditorRenderFrame);
  mapEditorRenderFrame = 0;
  drawMapEditor();
  syncMapEditorUi();
}

function initializeMapEditor(meta, snapshot) {
  if (meta?.manageable !== true) {
    detachMapEditor('이 점유 지도는 읽기 전용이므로 웹 편집 복사본을 생성할 수 없습니다.');
    return false;
  }
  if (meta?.editable !== true) {
    detachMapEditor(
      meta?.editable === false
        ? '이 점유 지도는 웹 편집을 지원하지 않습니다. P5 8-bit trinary YAML·PGM 지도만 안전하게 편집할 수 있습니다.'
        : '서버가 이 지도의 편집 가능 여부를 제공하지 않습니다. 안전을 위해 편집을 비활성화했습니다.',
    );
    return false;
  }
  if (!mapEditorEngine) {
    detachMapEditor('2D 편집 모듈을 불러오지 못했습니다. 페이지를 새로고침하세요.');
    return false;
  }
  const revision = mapEditorRevision(snapshot);
  if (!revision) {
    detachMapEditor('이 지도 응답에는 안전 편집용 revision 문자열이 없습니다. 서버 업데이트 후 다시 불러오세요.');
    return false;
  }
  if (mapEditorSession?.sourceId === meta.id) {
    if (mapEditorSession.revision === revision) return true;
    if (mapEditorSession.changedCount) {
      mapEditorSession.sourceStale = true;
      setMapEditorFeedback('편집 중 원본 revision이 변경되었습니다. 현재 편집은 유지되지만 저장하지 말고 새로 선택해 확인하세요.', true);
      syncMapEditorUi();
      return false;
    }
  }
  try {
    const cells = mapEditorEngine.decodeGrid(snapshot.data_b64, snapshot.width, snapshot.height);
    const session = {
      sourceId: meta.id,
      sourceName: meta.name || snapshot.name || 'Saved 2D map',
      revision,
      sourceStale: false,
      width: Number(snapshot.width),
      height: Number(snapshot.height),
      original: cells.slice(),
      cells,
      changedCount: 0,
      undo: [],
      redo: [],
      stroke: null,
      layout: null,
      sourceCanvas: null,
      sourceContext: null,
    };
    buildMapEditorSourceCanvas(session);
    mapEditorSession = session;
    mapEditorFeedback = null;
    mapEditorUnavailableReason = '';
    ui.mapEditorSaveName.value = suggestedDerivedMapName(meta, '_edited');
    drawMapEditor();
    syncMapEditorUi();
    return true;
  } catch (error) {
    detachMapEditor(`2D 지도 편집 준비 실패: ${error.message}`);
    return false;
  }
}

function mapEditorCellFromPointer(event) {
  const session = mapEditorSession;
  const layout = session?.layout;
  if (!session || !layout) return null;
  const bounds = ui.mapEditorCanvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return null;
  const x = (event.clientX - bounds.left) * (layout.canvasWidth / bounds.width);
  const y = (event.clientY - bounds.top) * (layout.canvasHeight / bounds.height);
  if (x < layout.left || y < layout.top || x >= layout.left + layout.drawWidth || y >= layout.top + layout.drawHeight) return null;
  return {
    x: Math.max(0, Math.min(session.width - 1, Math.floor((x - layout.left) / layout.scale))),
    y: Math.max(0, Math.min(session.height - 1, session.height - 1 - Math.floor((y - layout.top) / layout.scale))),
  };
}

function recordMapEditorChanges(changes) {
  const session = mapEditorSession;
  if (!session || !changes.length) return;
  for (const change of changes) {
    if (session.stroke && !session.stroke.before.has(change.index)) session.stroke.before.set(change.index, change.before);
    const original = session.original[change.index];
    const wasChanged = change.before !== original;
    const isChanged = change.after !== original;
    if (wasChanged !== isChanged) session.changedCount += isChanged ? 1 : -1;
  }
  updateMapEditorSourcePixels(changes);
  scheduleMapEditorDraw();
  mapEditorFeedback = null;
  syncMapEditorUi();
}

function paintMapEditorCell(cell) {
  const session = mapEditorSession;
  if (!session || !cell) return;
  const size = Number(ui.mapEditorBrushSize.value) || 1;
  const value = mapEditorTool === 'eraser'
    ? (index) => session.original[index]
    : mapEditorCellValue;
  const changes = mapEditorEngine.paintCircle(session.cells, session.width, session.height, cell.x, cell.y, size, value);
  recordMapEditorChanges(changes);
}

function beginMapEditorStroke(event) {
  if (event.button !== 0 || !mapEditorSession || mapEditorBusy || mapConversionPending || mapConversionCompleting) return;
  const cell = mapEditorCellFromPointer(event);
  if (!cell) return;
  event.preventDefault();
  try { ui.mapEditorCanvas.setPointerCapture(event.pointerId); } catch (_) {}
  mapEditorSession.stroke = { pointerId: event.pointerId, before: new Map(), last: cell };
  paintMapEditorCell(cell);
}

function moveMapEditorStroke(event) {
  const stroke = mapEditorSession?.stroke;
  if (!stroke || stroke.pointerId !== event.pointerId) return;
  const cell = mapEditorCellFromPointer(event);
  if (!cell) return;
  event.preventDefault();
  const spacing = Math.max(1, Math.floor((Number(ui.mapEditorBrushSize.value) || 1) / 3));
  for (const point of mapEditorEngine.interpolateCells(stroke.last, cell, spacing)) paintMapEditorCell(point);
  stroke.last = cell;
}

function finishMapEditorStroke(event) {
  const session = mapEditorSession;
  const stroke = session?.stroke;
  if (!stroke || stroke.pointerId !== event.pointerId) return;
  session.stroke = null;
  const patch = [];
  for (const [index, before] of stroke.before) {
    const after = session.cells[index];
    if (before !== after) patch.push({ index, before, after });
  }
  if (patch.length) {
    session.undo.push(patch);
    if (session.undo.length > 30) session.undo.shift();
    session.redo = [];
  }
  try { ui.mapEditorCanvas.releasePointerCapture(event.pointerId); } catch (_) {}
  syncMapEditorUi();
}

function applyMapEditorPatch(patch, direction) {
  const session = mapEditorSession;
  if (!session) return;
  const changes = [];
  for (const item of patch) {
    const before = session.cells[item.index];
    const after = direction === 'undo' ? item.before : item.after;
    if (before === after) continue;
    const original = session.original[item.index];
    const wasChanged = before !== original;
    const isChanged = after !== original;
    if (wasChanged !== isChanged) session.changedCount += isChanged ? 1 : -1;
    session.cells[item.index] = after;
    changes.push({ index: item.index, before, after });
  }
  updateMapEditorSourcePixels(changes);
  scheduleMapEditorDraw();
  mapEditorFeedback = null;
}

function undoMapEditor() {
  const session = mapEditorSession;
  if (!session || mapEditorBusy || !session.undo.length) return;
  const patch = session.undo.pop();
  applyMapEditorPatch(patch, 'undo');
  session.redo.push(patch);
  syncMapEditorUi();
}

function redoMapEditor() {
  const session = mapEditorSession;
  if (!session || mapEditorBusy || !session.redo.length) return;
  const patch = session.redo.pop();
  applyMapEditorPatch(patch, 'redo');
  session.undo.push(patch);
  syncMapEditorUi();
}

async function resetMapEditor() {
  const session = mapEditorSession;
  if (!session || mapEditorBusy || !session.changedCount) return;
  const reloadChangedSource = session.sourceStale;
  const sourceId = session.sourceId;
  const patch = [];
  for (let index = 0; index < session.cells.length; index += 1) {
    if (session.cells[index] !== session.original[index]) {
      patch.push({ index, before: session.cells[index], after: session.original[index] });
    }
  }
  applyMapEditorPatch(patch, 'redo');
  session.undo.push(patch);
  if (session.undo.length > 30) session.undo.shift();
  session.redo = [];
  syncMapEditorUi();
  if (reloadChangedSource) {
    setMapEditorFeedback('편집을 취소했습니다. 변경된 원본 revision을 다시 불러오고 있습니다.');
    clearSavedMapCache(sourceId);
    const loaded = await selectSavedMap(sourceId, false);
    if (!loaded) setMapEditorFeedback('변경된 원본 지도를 다시 불러오지 못했습니다. 목록을 새로고침한 뒤 다시 선택하세요.', true);
  }
}

function editorHasUnsavedChanges() {
  return Boolean(mapEditorSession?.changedCount);
}

function confirmDiscardMapEditor(message = '저장하지 않은 2D 지도 편집을 버릴까요?') {
  return !editorHasUnsavedChanges() || window.confirm(message);
}

async function saveMapEditorCopy() {
  const session = mapEditorSession;
  if (!session || mapEditorBusy || !session.changedCount) return;
  if (session.sourceStale) {
    showToast('원본 지도가 변경됐습니다. RESET해 새 revision을 불러온 뒤 다시 편집하세요.', true);
    return;
  }
  const name = ui.mapEditorSaveName.value.trim();
  if (!validSavedMapName(name)) { showToast('복사본 이름은 영문·숫자로 시작하고 영문·숫자·_·-만 사용할 수 있습니다.', true); return; }
  const runs = mapEditorEngine.diffRuns(session.original, session.cells);
  if (!runs.length) { showToast('저장할 변경 사항이 없습니다.'); return; }
  mapEditorBusy = true;
  setMapEditorFeedback(`${runs.length.toLocaleString()}개 변경 run을 새 복사본으로 저장하고 있습니다.`);
  syncMapEditorUi();
  let createdCopy = null;
  try {
    const response = await api(`/api/v1/saved-maps/${encodeURIComponent(session.sourceId)}/edited-copy`, {
      method: 'POST',
      body: JSON.stringify({
        name,
        source_revision: session.revision,
        runs,
      }),
    });
    const result = response.map || response;
    if (!result?.id) throw new Error('서버가 새 지도 ID를 반환하지 않았습니다.');
    createdCopy = result;
    savedMapSelectionGeneration += 1;
    detachMapEditor('편집 복사본을 저장했습니다. 새 지도를 불러오고 있습니다.');
    if (!savedMapCatalog.some((entry) => entry.id === result.id)) {
      savedMapCatalog = [...savedMapCatalog, result];
    }
    const loaded = await selectSavedMap(result.id, false, true);
    if (!loaded) throw new Error('복사본은 저장됐지만 대시보드에서 다시 불러오지 못했습니다.');
    setMapEditorFeedback(`${result.name || name} 복사본을 저장하고 선택했습니다.`);
    showToast(`${result.name || name} 편집 복사본을 저장했습니다.`);
  } catch (error) {
    setMapEditorFeedback(
      createdCopy
        ? `${createdCopy.name || name} 복사본은 저장됐지만 대시보드 재로드에 실패했습니다: ${error.message}`
        : `편집 복사본 저장 실패: ${error.message}`,
      true,
    );
  } finally {
    mapEditorBusy = false;
    syncMapEditorUi();
  }
}

function compactValue(value) {
  if (value == null) return '—';
  if (Array.isArray(value)) {
    const shown = value.slice(0, 4).map((item) => typeof item === 'number' ? Number(item).toFixed(2) : String(item));
    return `[${shown.join(', ')}${value.length > 4 ? '…' : ''}]`;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value).slice(0, 3).map(([key, item]) => `${key}:${typeof item === 'number' ? Number(item).toFixed(2) : item}`);
    return entries.join(' ');
  }
  if (typeof value === 'number') return Number(value).toFixed(Math.abs(value) >= 100 ? 0 : 2);
  return String(value);
}

function updateSensors(sensors) {
  const priority = ['robot_state', 'imu', 'lidar', 'battery', 'gnss', 'range', 'environment'];
  const rank = (sensor) => {
    const index = priority.indexOf(sensor.category);
    return index < 0 ? priority.length : index;
  };
  const sorted = [...sensors].sort((a, b) => rank(a) - rank(b) || String(a.topic).localeCompare(String(b.topic)));
  ui.sensorCount.textContent = `${sensors.length} streams`;
  if (!sorted.length) {
    ui.sensorGrid.innerHTML = '<div class="sensor-placeholder">센서 데이터를 기다리고 있습니다.</div>';
    return;
  }
  ui.sensorGrid.innerHTML = sorted.map((sensor) => {
    const values = Object.entries(sensor.values || {})
      .filter(([key]) => !key.startsWith('motor_'))
      .slice(0, 5)
      .map(([key, value]) => `<div class="sensor-value"><span>${escapeHtml(key.replaceAll('_', ' '))}</span><b>${escapeHtml(compactValue(value))}</b></div>`)
      .join('');
    return `<article class="sensor-card"><div class="sensor-card-head"><strong title="${escapeHtml(sensor.topic)}">${escapeHtml(sensor.topic)}</strong><span>${formatHz(sensor.hz)}</span></div><div class="sensor-values">${values || '<div class="sensor-value"><span>state</span><b>receiving</b></div>'}</div></article>`;
  }).join('');
}

function updateOdometry(sensors, source) {
  const snapshot = latestState?.robot_pose;
  const odom = sensors.find((sensor) => sensor.topic === source) || sensors.find((sensor) => sensor.category === 'odometry');
  ui.odomTopic.textContent = snapshot?.topic || source || odom?.topic || 'NO SOURCE';
  if (snapshot) {
    applyPoseSnapshot(snapshot);
    return;
  }
  updateMapPose(
    odom?.values?.position,
    odom?.values?.orientation,
    odom?.values?.frame_id,
    odom?.values?.linear_velocity,
    odom?.topic || source || '',
  );
}

function applyPoseSnapshot(snapshot) {
  ui.odomTopic.textContent = snapshot?.topic || latestState?.sources?.odometry || 'NO SOURCE';
  if (!robotRuntimeDataCompatible) {
    clearLivePose();
    return;
  }
  const signature = `${snapshot?.topic || ''}:${snapshot?.seq || 0}:${snapshot?.state || 'waiting'}`;
  if (signature === lastPoseSignature) return;
  lastPoseSignature = signature;
  if (snapshot?.state !== 'ok') {
    clearLivePose();
    return;
  }
  updateMapPose(
    snapshot.position,
    snapshot.orientation,
    snapshot.frame_id,
    snapshot.linear_velocity,
    snapshot.topic,
  );
}

function updateMapPose(position, orientation, frameId, velocity = null, topic = '') {
  const x = Number(position?.x);
  const y = Number(position?.y);
  const z = Number(position?.z);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  const rpy = quaternionRpy(orientation);
  const nextPose = {
    x,
    y,
    z: Number.isFinite(z) ? z : 0,
    roll: rpy[0],
    pitch: rpy[1],
    yaw: rpy[2],
    frameId: frameId || '',
    topic,
  };
  const previous = poseTrail[poseTrail.length - 1];
  const distance = previous ? Math.hypot(nextPose.x - previous.x, nextPose.y - previous.y) : Infinity;
  const turn = previous ? Math.abs(angleDelta(nextPose.yaw, previous.yaw)) : Infinity;
  if (!previous || distance > 0.025 || turn > 0.035) {
    poseTrail.push(nextPose);
    poseTrail = poseTrail.slice(-120);
  }
  if (!targetPose || targetPose.frameId !== nextPose.frameId || Math.hypot(targetPose.x - x, targetPose.y - y) > 5) {
    currentPose = { ...nextPose };
  }
  targetPose = nextPose;
  poseLive = true;
  lastPoseAt = Date.now();
  poseImuAnchor = Array.isArray(latestBodyRpy)
    ? { imuYaw: latestBodyRpy[2], odomYaw: nextPose.yaw }
    : null;
  const speed = Math.hypot(Number(velocity?.x || 0), Number(velocity?.y || 0), Number(velocity?.z || 0));
  ui.posX.textContent = safeNumber(x);
  ui.posY.textContent = safeNumber(y);
  ui.posZ.textContent = safeNumber(nextPose.z);
  ui.speed.textContent = safeNumber(speed);
}

function quaternionYaw(quaternion) {
  const x = Number(quaternion?.x) || 0;
  const y = Number(quaternion?.y) || 0;
  const z = Number(quaternion?.z) || 0;
  const w = Number(quaternion?.w);
  const normalizedW = Number.isFinite(w) ? w : 1;
  return Math.atan2(2 * (normalizedW * z + x * y), 1 - 2 * (y * y + z * z));
}

function quaternionRpy(quaternion) {
  const x = Number(quaternion?.x) || 0;
  const y = Number(quaternion?.y) || 0;
  const z = Number(quaternion?.z) || 0;
  const w = Number.isFinite(Number(quaternion?.w)) ? Number(quaternion.w) : 1;
  const roll = Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
  const sinPitch = Math.max(-1, Math.min(1, 2 * (w * y - z * x)));
  return [roll, Math.asin(sinPitch), quaternionYaw({ x, y, z, w })];
}

function clearLivePose() {
  poseLive = false;
  targetPose = null;
  currentPose = null;
  poseImuAnchor = null;
  ui.posX.textContent = ui.posY.textContent = ui.posZ.textContent = ui.speed.textContent = '—';
  if (activePage === 'mapping') {
    scene3d?.setRobotPose(null);
    liveMap2d?.setPose(null);
  }
}

function animateRobot(timestamp) {
  requestAnimationFrame(animateRobot);
  if (!lastMotionFrameAt) lastMotionFrameAt = timestamp;
  const elapsed = Math.min(Math.max((timestamp - lastMotionFrameAt) / 1000, 0), 0.2);
  if (elapsed < 1 / 30) return;
  lastMotionFrameAt = timestamp;

  if (targetJointPositions) {
    if (!renderedJointPositions || renderedJointPositions.length !== targetJointPositions.length) {
      renderedJointPositions = targetJointPositions.slice();
    } else {
      const alpha = 1 - Math.exp(-elapsed / 0.055);
      renderedJointPositions = renderedJointPositions.map((value, index) =>
        value + (targetJointPositions[index] - value) * alpha);
    }
  }

  if (targetPose) {
    if (!currentPose || currentPose.frameId !== targetPose.frameId) {
      currentPose = { ...targetPose };
    } else {
      const alpha = 1 - Math.exp(-elapsed / 0.09);
      currentPose = {
        ...targetPose,
        x: currentPose.x + (targetPose.x - currentPose.x) * alpha,
        y: currentPose.y + (targetPose.y - currentPose.y) * alpha,
        z: currentPose.z + (targetPose.z - currentPose.z) * alpha,
        roll: currentPose.roll + angleDelta(targetPose.roll, currentPose.roll) * alpha,
        pitch: currentPose.pitch + angleDelta(targetPose.pitch, currentPose.pitch) * alpha,
        yaw: currentPose.yaw + angleDelta(targetPose.yaw, currentPose.yaw) * alpha,
      };
    }
  }

  if (activePage === 'mapping' && desiredMapView() === 'cloud') {
    if (robotRuntimeDataCompatible && renderedJointPositions) scene3d?.setRobotJointPositions?.(renderedJointPositions);
    scene3d?.setRobotPose(robotRuntimeDataCompatible && poseLive ? currentPose : null);
  } else if (activePage === 'mapping' && desiredMapView() === 'projection') {
    liveMap2d?.setPose(robotRuntimeDataCompatible && poseLive ? currentPose : null);
    liveMap2d?.setTrail(robotRuntimeDataCompatible ? poseTrail : []);
  } else if (activePage === 'navigation' && robotRuntimeDataCompatible && robotModelsReady && !robotModelsFailed && selectedRobotType === 'go2' && jointLive && renderedJointPositions) {
    navigationScene3d?.setRobotJointPositions?.(renderedJointPositions);
  }
}

function angleDelta(a, b) {
  return Math.atan2(Math.sin(a - b), Math.cos(a - b));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

function renderTopics() {
  const query = ui.topicSearch.value.trim().toLowerCase();
  const category = ui.categoryFilter.value;
  const rows = latestTopics.filter((topic) => {
    const matchesText = !query || `${topic.name} ${topic.type}`.toLowerCase().includes(query);
    return matchesText && (!category || topic.category === category);
  });
  if (!rows.length) {
    ui.topicsBody.innerHTML = '<tr><td colspan="6" class="table-empty">조건에 맞는 토픽이 없습니다.</td></tr>';
    return;
  }
  ui.topicsBody.innerHTML = rows.map((topic) => `
    <tr>
      <td><span class="state-pill ${topic.state}">${topic.state}</span></td>
      <td class="topic-name">${topic.selected ? '◆ ' : ''}${escapeHtml(topic.name)}</td>
      <td class="topic-type">${escapeHtml(topic.type || topic.types?.join(', ') || 'type conflict')}</td>
      <td><span class="category-tag">${escapeHtml(topic.category)}</span></td>
      <td>${topic.hz == null ? '—' : topic.hz.toFixed(2)}</td>
      <td>${topic.age_s == null ? '—' : `${topic.age_s.toFixed(2)}s`}</td>
    </tr>`).join('');
}

function fillSourceSelect(select, options, selected, emptyLabel) {
  const html = [`<option value="">${emptyLabel}</option>`]
    .concat((options || []).map((item) => `<option value="${escapeHtml(item.topic)}">${escapeHtml(item.topic)}</option>`))
    .join('');
  select.innerHTML = html;
  select.value = LidarSourceIdentity.topicOf(selected);
}

function pointcloudMetadataForTopic(index, topic) {
  if (!index || !topic) return {};
  if (Array.isArray(index)) {
    const match = index.find((entry) => LidarSourceIdentity.topicOf(entry) === topic);
    return LidarSourceIdentity.flattenMetadata(match);
  }
  if (typeof index !== 'object') return {};
  return LidarSourceIdentity.flattenMetadata(index[topic] || index.topics?.[topic]);
}

function pointcloudMetadataIndex(payload) {
  return payload?.pointcloud_metadata
    || payload?.source_metadata?.pointcloud
    || payload?.metadata?.pointcloud
    || payload?.metadata?.sources?.pointcloud
    || {};
}

function fillPointcloudSourceSelect(select, options, selected, metadataIndex = {}) {
  const selectedTopic = LidarSourceIdentity.topicOf(selected);
  const entries = new Map();
  for (const item of options || []) {
    const topic = LidarSourceIdentity.topicOf(item);
    if (!topic) continue;
    const metadata = Object.assign(
      {},
      LidarSourceIdentity.flattenMetadata(item),
      pointcloudMetadataForTopic(metadataIndex, topic),
    );
    entries.set(topic, { topic, metadata, identity: LidarSourceIdentity.describe(topic, metadata) });
  }
  if (selectedTopic && !entries.has(selectedTopic)) {
    const metadata = Object.assign(
      {},
      LidarSourceIdentity.flattenMetadata(selected),
      pointcloudMetadataForTopic(metadataIndex, selectedTopic),
    );
    entries.set(selectedTopic, {
      topic: selectedTopic,
      metadata,
      identity: LidarSourceIdentity.describe(selectedTopic, metadata),
    });
  }
  pointcloudSourceCatalog = entries;
  pointcloudSourcesLoaded = true;

  const emptyOption = document.createElement('option');
  emptyOption.value = '';
  emptyOption.textContent = 'PointCloud 없음';
  select.replaceChildren(emptyOption);

  const grouped = new Map();
  for (const entry of entries.values()) {
    const label = LidarSourceIdentity.groupLabel(entry.identity);
    if (!grouped.has(label)) grouped.set(label, []);
    grouped.get(label).push(entry);
  }
  const groupOrder = ['GO2 BUILT-IN LIDAR', 'HESAI XT16'];
  const sortedGroups = Array.from(grouped.entries()).sort(([left], [right]) => {
    const leftRank = groupOrder.includes(left) ? groupOrder.indexOf(left) : groupOrder.length;
    const rightRank = groupOrder.includes(right) ? groupOrder.indexOf(right) : groupOrder.length;
    return leftRank - rightRank || left.localeCompare(right);
  });
  for (const [label, groupEntries] of sortedGroups) {
    const group = document.createElement('optgroup');
    group.label = label;
    for (const entry of groupEntries) {
      const option = document.createElement('option');
      option.value = entry.topic;
      option.textContent = `${entry.identity.stageLabel} · ${entry.topic}`;
      option.title = `${entry.identity.sensorLabel} · ${entry.identity.stageLabel} · ${entry.topic}`;
      option.dataset.sensorId = entry.identity.sensorId;
      option.dataset.pipelineStage = entry.identity.stage;
      group.append(option);
    }
    select.append(group);
  }
  select.value = selectedTopic;
  renderLidarSourceIdentity();
}

function selectedPointcloudTopic() {
  if (pointcloudSourcesLoaded) return LidarSourceIdentity.topicOf(ui.cloudSource.value);
  return LidarSourceIdentity.topicOf(latestState?.sources?.pointcloud);
}

function lidarSourcePinInfo(topic, catalogEntry, selection = pointcloudSelection) {
  if (!topic) return { pinned: false, label: '', defaultPin: false, title: '' };
  const metadata = catalogEntry?.metadata || {};
  const requested = LidarSourceIdentity.topicOf(selection?.requested);
  const contractPinned = selection?.mode === 'pinned' && requested === topic;
  const descriptorPinned = metadata.pinned === true;
  if (!contractPinned && !descriptorPinned) {
    return { pinned: false, label: '', defaultPin: false, title: '' };
  }
  const origin = String(contractPinned ? selection?.origin || '' : metadata.selection_origin || '');
  const defaultPin = origin === 'profile_default';
  return {
    pinned: true,
    label: defaultPin ? 'DEFAULT PIN' : 'PINNED',
    defaultPin,
    title: defaultPin
      ? '프로필 기본 LiDAR로 고정됨 · 퍼블리셔가 없어도 다른 센서로 자동 전환하지 않습니다.'
      : '선택한 LiDAR로 고정됨 · 퍼블리셔가 없어도 다른 센서로 자동 전환하지 않습니다.',
  };
}

function lidarSourceFreshness(topic, catalogEntry, forceStatus = '') {
  if (forceStatus) return forceStatus;
  if (!topic) return 'WAITING';
  const pinInfo = lidarSourcePinInfo(topic, catalogEntry);
  const configuredPublishers = catalogEntry?.metadata?.publishers;
  if (pinInfo.pinned && configuredPublishers != null && Number(configuredPublishers) === 0) {
    return 'WAITING';
  }
  const frameTopic = LidarSourceIdentity.topicOf(lastCloudSnapshot);
  const frameAge = pointcloudLastFrameAt ? Date.now() - pointcloudLastFrameAt : null;
  if (pointcloudTransportWanted() && !lastCloudSnapshot?.offline_snapshot && frameTopic === topic && frameAge != null) {
    return frameAge <= 5000 ? 'LIVE' : 'STALE';
  }
  const stateTopic = LidarSourceIdentity.topicOf(latestState?.sources?.pointcloud);
  const currentStateMatches = stateTopic === topic;
  const topicMetric = latestTopics.find((entry) => entry.name === topic);
  const statusCandidates = currentStateMatches
    ? [latestState?.cloud?.state, latestState?.mapping?.cloud?.state, topicMetric?.state, catalogEntry?.identity?.reportedStatus]
    : [topicMetric?.state, catalogEntry?.identity?.reportedStatus];
  for (const status of statusCandidates) {
    const normalized = status === 'LIVE' || status === 'WAITING' || status === 'STALE'
      ? status
      : LidarSourceIdentity.normalizeReportedStatus(status);
    if (normalized) return normalized;
  }
  const age = Number(topicMetric?.age_s);
  if (topicMetric?.age_s != null && Number.isFinite(age) && age > 5) return 'STALE';
  return 'WAITING';
}

function renderLidarSourceReadout(elements, identity, freshness, pinInfo) {
  if (!elements.sensor || !elements.pin || !elements.topic || !elements.stage || !elements.freshness) return;
  const sensorClass = identity.sensorId === 'go2_builtin_lidar'
    ? 'go2'
    : identity.sensorId === 'hesai_xt16' ? 'hesai' : 'generic';
  elements.sensor.className = `lidar-sensor-badge ${sensorClass}`;
  elements.sensor.textContent = identity.sensorLabel;
  elements.sensor.dataset.sensorId = identity.sensorId;
  elements.pin.className = `lidar-source-pin${pinInfo.defaultPin ? ' default-pin' : ''}${pinInfo.pinned ? '' : ' is-hidden'}`;
  elements.pin.textContent = pinInfo.label || 'PINNED';
  elements.pin.title = pinInfo.title;
  elements.topic.textContent = identity.topic || 'NO POINTCLOUD TOPIC';
  elements.topic.title = identity.topic || '선택된 PointCloud 토픽이 없습니다.';
  elements.stage.textContent = identity.stageLabel;
  elements.stage.dataset.pipelineStage = identity.stage;
  elements.freshness.className = `lidar-source-freshness ${freshness.toLowerCase()}`;
  elements.freshness.textContent = freshness;
}

function renderLidarSourceIdentity(forceStatus = '') {
  const telemetryUnavailable = overviewTelemetryAvailability === false
    || (latestState && !overviewTelemetryLive(latestState.health));
  if (telemetryUnavailable) {
    ui.lidarSub.textContent = latestState
      ? overviewUnavailableReason(latestState.health)
      : '에이전트 연결 끊김';
    ui.lidarSub.title = ui.lidarSub.textContent;
    return;
  }
  const topic = selectedPointcloudTopic();
  const catalogEntry = pointcloudSourceCatalog.get(topic);
  const topicMetric = latestTopics.find((entry) => entry.name === topic);
  const stateTopic = LidarSourceIdentity.topicOf(latestState?.sources?.pointcloud);
  const runtimeMetadata = stateTopic === topic
    ? Object.assign(
      {},
      LidarSourceIdentity.flattenMetadata(latestState?.mapping?.cloud),
      LidarSourceIdentity.flattenMetadata(latestState?.cloud),
    )
    : {};
  const metadata = Object.assign(
    {},
    catalogEntry?.metadata || {},
    LidarSourceIdentity.flattenMetadata(topicMetric),
    runtimeMetadata,
  );
  const identity = LidarSourceIdentity.describe(topic, metadata);
  const freshness = lidarSourceFreshness(topic, catalogEntry, forceStatus);
  const pinInfo = lidarSourcePinInfo(topic, catalogEntry);
  renderLidarSourceReadout({
    sensor: ui.cloudSourceSensorBadge,
    pin: ui.cloudSourcePin,
    topic: ui.cloudSourceTopicLabel,
    stage: ui.cloudSourceStageLabel,
    freshness: ui.cloudSourceFreshness,
  }, identity, freshness, pinInfo);
  renderLidarSourceReadout({
    sensor: ui.mappingLidarSensorBadge,
    pin: ui.mappingLidarPin,
    topic: ui.mappingLidarTopic,
    stage: ui.mappingLidarStage,
    freshness: ui.mappingLidarFreshness,
  }, identity, freshness, pinInfo);
  ui.lidarSub.textContent = `${identity.sensorLabel} · ${identity.stageLabel} · ${identity.topic || 'NO SOURCE'}`;
  ui.lidarSub.title = ui.lidarSub.textContent;
}

async function refreshSources() {
  try {
    const payload = await api('/api/v1/sources');
    const fingerprint = JSON.stringify(payload);
    if (fingerprint === sourceFingerprint) return;
    sourceFingerprint = fingerprint;
    pointcloudSelection = payload.selection?.pointcloud || {};
    fillSourceSelect(ui.cameraSource, payload.options.camera, payload.selected.camera, '카메라 없음');
    ui.cameraSource.disabled = Boolean(payload.locked?.camera);
    ui.cameraSource.title = payload.locked?.camera
      ? 'Go2 직접 멀티캐스트 카메라는 실행 프로필에서 고정됩니다.'
      : '';
    fillPointcloudSourceSelect(
      ui.cloudSource,
      payload.options.pointcloud,
      payload.selected_descriptors?.pointcloud || payload.selected.pointcloud,
      pointcloudMetadataIndex(payload),
    );
    fillSourceSelect(ui.odomSource, payload.options.odometry, payload.selected.odometry, 'Odometry 없음');
    fillSourceSelect(ui.mapSource, payload.options.occupancy_grid, payload.selected.occupancy_grid, '2D 맵 없음');
  } catch (error) { console.warn(error); }
}

async function selectSource(kind, value) {
  try {
    await api('/api/v1/sources', { method: 'POST', body: JSON.stringify({ [kind]: value }) });
    showToast(`${kind} 소스를 변경했습니다.`);
    sourceFingerprint = '';
  } catch (error) { showToast(`소스 변경 실패: ${error.message}`, true); }
}

async function refreshState() {
  const generation = ++stateRequestGeneration;
  try {
    const state = await api('/api/v1/state');
    if (generation !== stateRequestGeneration) return null;
    latestState = state;
    updateOverview(state);
    if (activePage === 'mapping') redrawActiveMap();
    if (activePage === 'maps') redrawSavedMap();
    return state;
  } catch (error) {
    if (generation !== stateRequestGeneration) return null;
    latestState = null;
    ui.connectionChip.className = 'connection-chip error';
    ui.connectionLabel.textContent = '에이전트 연결 끊김';
    renderOverviewUnavailable('에이전트 연결 끊김');
    renderLidarSourceIdentity('STALE');
    ui.lastUpdated.textContent = `Last update failed · ${new Date().toLocaleTimeString('ko-KR', { hour12: false })}`;
    if (scene3d) scene3d.setStatus({ online: false, lidarOnline: false, message: '에이전트 연결이 끊겼습니다' });
    return null;
  }
}

function generatedMapName() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `map_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function hasFreshLaserMap() {
  const pipelineState = String(mappingControlSnapshot?.pipeline?.state || 'idle');
  // A previous graph sample can remain cached for a few refresh ticks while a
  // new FAST-LIO process group is still starting (or being torn down).  Never
  // let that stale sample authorize a save across a session boundary.
  if (pipelineState === 'starting' || pipelineState === 'stopping') return false;
  const topic = latestTopics.find((item) => item.name === '/Laser_map');
  if (topic?.state === 'ok') return true;
  const hasPublisher = Number(topic?.publishers || 0) > 0;
  if (!hasPublisher) return false;
  // The dashboard-owned launcher does not report RUNNING until it has
  // observed a non-empty /Laser_map after validating every XT16, bridge and
  // FAST-LIO gate.  That readiness must not depend on the pointcloud chosen
  // purely for visualization (for example /velodyne_points).
  if (pipelineState === 'running') return true;
  // The live renderer deliberately subscribes to the much smaller
  // /cloud_registered stream.  /Laser_map is therefore not metered by the
  // dashboard, even though FAST-LIO is publishing it.  A live registered scan,
  // matching FAST-LIO odometry, and a Laser_map publisher together are a safe
  // readiness signal; the saver still waits for and validates an actual map.
  return latestState?.sources?.pointcloud === '/cloud_registered' &&
    latestState?.sources?.odometry === '/Odometry' &&
    latestState?.mapping?.cloud?.state === 'ok' &&
    latestState?.mapping?.odometry?.state === 'ok';
}

function mappingPipelineActive() {
  return ['starting', 'running', 'stopping'].includes(mappingControlSnapshot?.pipeline?.state);
}

function scheduleMappingLogScroll(scrollSnapshot) {
  scheduleStickyLogScroll(ui.mappingLog, scrollSnapshot, {
    shouldApply: () => activePage === 'mapping',
  });
}

function renderMappingControl() {
  if (!mappingControlSnapshot) return;
  const logScrollSnapshot = captureStickyLogScroll(ui.mappingLog);
  const pipeline = mappingControlSnapshot.pipeline || {};
  const operation = mappingControlSnapshot.operation || {};
  const laserMapReady = hasFreshLaserMap();
  const lidarLive = latestState?.mapping?.cloud?.state === 'ok';
  const pipelineActive = mappingPipelineActive();
  const saving = operation.state === 'saving';
  const external = laserMapReady && !pipelineActive;

  ui.mappingPipelineLabel.textContent = external ? 'EXTERNAL · LIVE' : String(pipeline.state || 'idle').toUpperCase();
  ui.mappingDataLabel.textContent = laserMapReady ? 'LASER_MAP READY' : lidarLive ? 'LIDAR LIVE · MAP WAITING' : 'WAITING';
  ui.mappingSaveLabel.textContent = operation.state === 'succeeded'
    ? (operation.files || []).join(' · ')
    : operation.state === 'failed' ? 'FAILED' : operation.map_name || '—';

  if (saving) {
    setStatePill(ui.mappingControlState, 'waiting', 'SAVING');
    ui.mappingOperationMessage.textContent = `${operation.map_name || 'map'} 저장 및 검증을 진행하고 있습니다.`;
  } else if (pipeline.state === 'failed' && !external) {
    setStatePill(ui.mappingControlState, 'error', 'START FAILED');
    ui.mappingOperationMessage.textContent = pipeline.error || '매핑 파이프라인이 종료되었습니다. 로그를 확인하세요.';
  } else if (operation.state === 'failed') {
    setStatePill(ui.mappingControlState, 'error', 'SAVE FAILED');
    ui.mappingOperationMessage.textContent = operation.error || '지도 저장 또는 검증에 실패했습니다.';
  } else if (laserMapReady) {
    setStatePill(ui.mappingControlState, 'ok', external ? 'EXTERNAL MAPPING' : 'MAPPING READY');
    ui.mappingOperationMessage.textContent = external
      ? '터미널에서 시작된 매핑을 감지했습니다. 현재 맵 저장은 가능하며 중지는 시작한 터미널에서 해야 합니다.'
      : '누적 /Laser_map이 정상입니다. 지금 3D PCD와 선택한 2D 지도를 저장할 수 있습니다.';
  } else if (pipelineActive) {
    setStatePill(ui.mappingControlState, 'waiting', 'DATA WAITING');
    ui.mappingOperationMessage.textContent = '프로세스는 시작됐지만 /Laser_map 데이터가 아직 없습니다. 케이블과 XT16 입력을 확인하세요.';
  } else if (operation.state === 'succeeded') {
    setStatePill(ui.mappingControlState, 'ok', 'SAVED');
    ui.mappingOperationMessage.textContent = `${operation.map_name} 저장과 결과 검증이 완료되었습니다.`;
  } else {
    setStatePill(ui.mappingControlState, 'waiting', 'IDLE');
    ui.mappingOperationMessage.textContent = '로봇과 XT16 연결 후 새 매핑을 시작할 수 있습니다.';
  }

  ui.mappingStartButton.textContent = external ? '외부 세션 동작 중' : pipelineActive ? '새 세션 재시작' : '새 맵 시작';
  ui.mappingStartButton.disabled = saving || external || pipeline.state === 'stopping';
  ui.mappingSaveButton.disabled = saving || !laserMapReady;
  ui.mappingStopButton.disabled = saving || !pipelineActive || pipeline.state === 'stopping';
  ui.mappingSessionName.disabled = saving;
  ui.mappingCreate2d.disabled = saving;

  ui.mappingLog.textContent = mappingLogLines.length
    ? mappingLogLines.join('\n')
    : '[Robot Scope] mapping console ready';
  scheduleMappingLogScroll(logScrollSnapshot);

  if (operation.kind !== 'pcd_to_2d' && operation.job_id && ['succeeded', 'failed'].includes(operation.state) && !mapConversionMatches(operation)) {
    const key = `${operation.job_id}:${operation.state}`;
    if (handledMappingOperation !== key) {
      handledMappingOperation = key;
      if (operation.state === 'succeeded') {
        showToast(`${operation.map_name} 지도를 저장했습니다.`);
        ui.mappingSessionName.value = generatedMapName();
        savedMapDataCache.clear();
        refreshSavedMaps();
      } else {
        showToast(`지도 저장 실패: ${operation.error || '로그를 확인하세요.'}`, true);
      }
    }
  }
  renderMapConversionOperation(operation);
}

async function refreshMappingControl() {
  const requestGeneration = mappingControlRequestGeneration;
  try {
    const payload = await api(`/api/v1/mapping/control?since_log_seq=${mappingLogCursor}`);
    if (requestGeneration !== mappingControlRequestGeneration) return;
    if (payload.logs_truncated) mappingLogLines = [];
    for (const entry of payload.logs || []) {
      const time = entry.at ? new Date(entry.at).toLocaleTimeString('ko-KR', { hour12: false }) : '--:--:--';
      mappingLogLines.push(`[${time}] ${String(entry.message || '')}`);
    }
    mappingLogLines = mappingLogLines.slice(-80);
    mappingLogCursor = Number(payload.log_cursor || mappingLogCursor);
    mappingControlSnapshot = payload;
    renderMappingControl();
  } catch (error) {
    if (requestGeneration !== mappingControlRequestGeneration) return;
    if (mapConversionTrackingExpired()) {
      failMapConversionTracking('15분 동안 변환 상태를 확인하지 못해 추적을 중단했습니다. 서버가 다시 연결되면 매핑 로그와 Saved Maps를 확인하세요.');
    }
    ui.mappingStartButton.disabled = ui.mappingSaveButton.disabled = ui.mappingStopButton.disabled = true;
    setStatePill(ui.mappingControlState, 'error', 'UNAVAILABLE');
    ui.mappingOperationMessage.textContent = `매핑 제어를 사용할 수 없습니다: ${error.message}`;
  }
}

async function startMappingSession() {
  const active = mappingPipelineActive();
  const warning = active
    ? '저장하지 않은 현재 누적 지도를 지우고 새 FAST-LIO 세션을 시작할까요?'
    : '새 맵 시작은 기존 Hesai·FAST-LIO 프로세스를 정리하고 누적 지도를 처음부터 만듭니다. 계속할까요?';
  if (!window.confirm(warning)) return;
  ui.mappingStartButton.disabled = true;
  try {
    if (active) await api('/api/v1/mapping/stop', { method: 'POST', body: '{}' });
    await api('/api/v1/mapping/start', { method: 'POST', body: '{}' });
    resetPointcloudStream(pointcloudStreamId);
    poseTrail = [];
    scene3d?.clearTrail();
    liveMap2d?.setTrail([]);
    liveMap2d?.setPose(null);
    showToast(active ? '새 매핑 세션을 시작했습니다.' : 'Hesai + FAST-LIO 시작을 요청했습니다.');
  } catch (error) {
    showToast(`매핑 시작 실패: ${error.message}`, true);
  } finally {
    await refreshMappingControl();
  }
}

async function saveMappingSession() {
  const name = ui.mappingSessionName.value.trim() || generatedMapName();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name)) {
    showToast('지도 이름은 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.', true);
    return;
  }
  ui.mappingSessionName.value = name;
  ui.mappingSaveButton.disabled = true;
  try {
    await api('/api/v1/mapping/save', {
      method: 'POST',
      body: JSON.stringify({ name, create_2d: ui.mappingCreate2d.checked }),
    });
    showToast('지도 캡처와 저장을 시작했습니다.');
  } catch (error) {
    showToast(`지도 저장 시작 실패: ${error.message}`, true);
  } finally {
    setTimeout(refreshMappingControl, 120);
  }
}

async function stopMappingSession() {
  if (hasFreshLaserMap() && !window.confirm('저장하지 않은 누적 지도는 사라집니다. 매핑을 중지할까요?')) return;
  ui.mappingStopButton.disabled = true;
  try {
    await api('/api/v1/mapping/stop', { method: 'POST', body: '{}' });
    showToast('대시보드가 시작한 매핑 프로세스를 중지했습니다.');
  } catch (error) {
    showToast(`매핑 중지 실패: ${error.message}`, true);
  } finally {
    await refreshMappingControl();
  }
}

async function refreshTopics() {
  try {
    latestTopics = (await api('/api/v1/topics')).topics || [];
    renderTopics();
    if (latestState) updateOverview(latestState);
    renderMappingControl();
  } catch (error) { console.warn(error); }
}

function resizeCanvas(canvas) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
  const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { width, height, ratio };
}

function pointcloudTransportWanted() {
  return activePage === 'mapping' && !document.hidden && desiredMapView() !== 'occupancy';
}

function resetPointcloudStream(streamId = '') {
  pointcloudStreamId = String(streamId || '');
  cloudSeq = -1;
  pointcloudLastFrameAt = 0;
  lastCloudSnapshot = null;
  resetLiveCloudAccumulator();
  sceneCloudDataKey = '';
  sceneCloudSourceKey = '';
  liveMap2dDataKey = '';
  liveMap2dSourceKey = '';
  scene3d?.clearPointCloud();
  liveMap2d?.clearPointCloud();
}

function applyPointcloudSnapshot(cloud) {
  const sequence = Number(cloud?.seq);
  if (!Number.isSafeInteger(sequence) || sequence <= 0 || !cloud.points?.length) return false;
  const incomingStreamId = String(cloud.stream_id || '');
  const streamChanged = Boolean(incomingStreamId && pointcloudStreamId && incomingStreamId !== pointcloudStreamId);
  const legacySequenceRollback = !incomingStreamId && cloudSeq >= 0 && sequence < Number(cloudSeq);
  if (streamChanged || legacySequenceRollback) resetPointcloudStream(incomingStreamId);
  if (incomingStreamId && !pointcloudStreamId) pointcloudStreamId = incomingStreamId;
  if (sequence <= Number(cloudSeq)) return false;
  cloudSeq = sequence;
  pointcloudLastFrameAt = Date.now();
  lastCloudSnapshot = accumulateRegisteredCloud(cloud);
  renderLidarSourceIdentity();
  if (activePage === 'mapping') {
    const view = desiredMapView();
    if (view === 'cloud') drawPointcloud(lastCloudSnapshot);
    else if (view === 'projection') drawLivePointProjection(lastCloudSnapshot);
  }
  return true;
}

function drainPointcloudFrame() {
  pointcloudFrameScheduled = false;
  const pending = pointcloudPendingFrame;
  pointcloudPendingFrame = null;
  if (pending && pending.generation === pointcloudSocketGeneration && pointcloudTransportWanted()) {
    try {
      applyPointcloudSnapshot(window.RobotPointCloudStream.decodeFrame(pending.buffer));
    } catch (error) {
      console.warn('point-cloud stream:', error);
    }
  }
  if (pointcloudPendingFrame && !pointcloudFrameScheduled) {
    pointcloudFrameScheduled = true;
    requestAnimationFrame(drainPointcloudFrame);
  }
}

function queuePointcloudFrame(buffer, generation) {
  pointcloudPendingFrame = { buffer, generation };
  if (pointcloudFrameScheduled) return;
  pointcloudFrameScheduled = true;
  requestAnimationFrame(drainPointcloudFrame);
}

function disconnectPointcloud() {
  pointcloudRequestGeneration += 1;
  pointcloudSocketGeneration += 1;
  clearTimeout(pointcloudReconnectTimer);
  pointcloudReconnectTimer = 0;
  pointcloudPendingFrame = null;
  const socket = pointcloudSocket;
  pointcloudSocket = null;
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) socket.close(1000, 'mapping view inactive');
}

function connectPointcloud() {
  if (!pointcloudTransportWanted() || !window.RobotPointCloudStream?.decodeFrame) return;
  if (pointcloudSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(pointcloudSocket.readyState)) return;
  const generation = ++pointcloudSocketGeneration;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/pointcloud`);
  pointcloudSocket = socket;
  socket.binaryType = 'arraybuffer';
  socket.onmessage = (event) => {
    if (pointcloudSocket !== socket || generation !== pointcloudSocketGeneration || !(event.data instanceof ArrayBuffer)) return;
    queuePointcloudFrame(event.data, generation);
  };
  socket.onclose = () => {
    if (pointcloudSocket !== socket || generation !== pointcloudSocketGeneration) return;
    pointcloudSocket = null;
    if (pointcloudTransportWanted()) {
      pointcloudReconnectTimer = setTimeout(() => {
        pointcloudReconnectTimer = 0;
        connectPointcloud();
      }, 1200);
    }
  };
  socket.onerror = () => socket.close();
}

function syncPointcloudTransport() {
  if (pointcloudTransportWanted()) connectPointcloud();
  else disconnectPointcloud();
}

async function latestBinaryPointcloud(seq) {
  const response = await fetch(`/api/v1/pointcloud.bin?since=${encodeURIComponent(seq)}`, { cache: 'no-store' });
  if (response.status === 204) return null;
  if (response.status === 404 || response.status === 415) {
    pointcloudBinaryHttpAvailable = false;
    return latestApi('/api/v1/pointcloud', seq);
  }
  if (!response.ok) throw new Error(String(response.status));
  return window.RobotPointCloudStream.decodeFrame(await response.arrayBuffer());
}

async function refreshPointcloud() {
  if (!pointcloudTransportWanted()) return;
  if (pointcloudSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(pointcloudSocket.readyState)) return;
  if (pointcloudRequestInFlight) return;
  pointcloudRequestInFlight = true;
  const generation = pointcloudRequestGeneration;
  try {
    const cloud = pointcloudBinaryHttpAvailable && window.RobotPointCloudStream?.decodeFrame
      ? await latestBinaryPointcloud(cloudSeq)
      : await latestApi('/api/v1/pointcloud', cloudSeq);
    if (generation !== pointcloudRequestGeneration) return;
    if (!cloud?.seq || !cloud.points?.length) {
      if (activePage === 'mapping' && desiredMapView() === 'cloud') drawPointcloud(lastCloudSnapshot);
      else if (activePage === 'mapping' && desiredMapView() === 'projection') drawLivePointProjection(lastCloudSnapshot);
      return;
    }
    applyPointcloudSnapshot(cloud);
  } catch (_) {
    if (activePage === 'mapping' && desiredMapView() === 'cloud') drawPointcloud(null);
    else if (activePage === 'mapping' && desiredMapView() === 'projection') drawLivePointProjection(null);
  } finally {
    pointcloudRequestInFlight = false;
  }
}

async function loadOfflinePointcloud() {
  try {
    const response = await fetch('/static/data/go2_saved_map.json', { cache: 'force-cache' });
    if (!response.ok) throw new Error(String(response.status));
    const cloud = await response.json();
    if (!cloud?.points?.length) throw new Error('empty snapshot');
    offlineCloudSnapshot = { ...cloud, offline_snapshot: true };
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    if (latestState) updateOverview(latestState);
  } catch (error) {
    console.info('offline 3D map unavailable; using generated demo cloud:', error);
    offlineCloudSnapshot = buildDemoPointcloud();
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    if (latestState) updateOverview(latestState);
  }
}

async function refreshSavedMaps() {
  try {
    const payload = await api('/api/v1/saved-maps');
    const maps = Array.isArray(payload.maps) ? payload.maps : [];
    savedMapCatalog = maps;
    await syncNavigationMapOptions();
    const preserved = maps.find((entry) => entry.id === selectedSavedMapId);
    if (editorHasUnsavedChanges() && mapEditorSession?.sourceId === selectedSavedMapId &&
        (!preserved || preserved.revision !== mapEditorSession.revision)) {
      mapEditorSession.sourceStale = true;
      if (preserved) selectedSavedMapMeta = preserved;
      setMapEditorFeedback(
        preserved
          ? '자동 새로고침에서 원본 revision 변경을 감지했습니다. 편집 내용은 유지했습니다. RESET 후 지도를 다시 선택하세요.'
          : '편집 중인 원본이 목록에서 사라졌습니다. 현재 변경은 유지되지만 새 복사본 저장은 실패할 수 있습니다.',
        true,
      );
      updateSavedMapOverview();
      syncMapEditorUi();
      return;
    }
    const keepFallback = selectedSavedMapId === '__fallback_cloud' && offlineCloudSnapshot &&
      !maps.some((entry) => entry.kind === 'pointcloud3d');
    const next = keepFallback ? null : (preserved || maps[0] || null);
    if (preserved) selectedSavedMapMeta = preserved;
    if (next && (next.id !== selectedSavedMapId || !savedMapDataCache.has(pointBudgetCacheKey(next.id, savedPointLimit, next.kind, next.revision)))) {
      await selectSavedMap(next.id, false);
      return;
    }
    if (!next) {
      selectedSavedMapId = offlineCloudSnapshot ? '__fallback_cloud' : '';
      selectedSavedMapMeta = offlineCloudSnapshot ? {
        id: '__fallback_cloud', name: offlineCloudSnapshot.demo_snapshot ? 'Public demo cloud' : 'Saved point cloud',
        kind: 'pointcloud3d', file_name: offlineCloudSnapshot.topic || '/saved/map', frame_id: offlineCloudSnapshot.frame_id,
      } : null;
      savedMapViewPreference = 'cloud';
    }
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
  } catch (error) {
    console.info('saved map catalog unavailable; using bundled fallback:', error);
    updateSavedMapOverview();
  }
}

async function selectSavedMap(mapId, notify = true, rethrow = false) {
  const switchingEditorSource = Boolean(mapEditorSession && mapEditorSession.sourceId !== mapId);
  if (switchingEditorSource && editorHasUnsavedChanges() && !mapEditorBusy &&
      !confirmDiscardMapEditor('저장하지 않은 2D 편집을 버리고 다른 지도를 선택할까요?')) return false;
  if (mapId === '__fallback_cloud') {
    savedMapSelectionGeneration += 1;
    if (switchingEditorSource) detachMapEditor('번들 3D 데모 지도는 2D 편집할 수 없습니다.');
    selectedSavedMapId = mapId;
    selectedSavedMapMeta = savedMapCatalog.find((entry) => entry.id === mapId) || {
      id: mapId, name: offlineCloudSnapshot?.demo_snapshot ? 'Public demo cloud' : 'Saved point cloud',
      kind: 'pointcloud3d', file_name: offlineCloudSnapshot?.topic || '/saved/map', frame_id: offlineCloudSnapshot?.frame_id,
    };
    savedMapViewPreference = 'cloud';
    ui.savedMapViewMode.value = 'cloud';
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    return true;
  }
  const meta = savedMapCatalog.find((entry) => entry.id === mapId);
  if (!meta) return;
  const loadGeneration = ++savedMapSelectionGeneration;
  const expectedRevision = String(meta.revision || '');
  const loadIsCurrent = () => (
    loadGeneration === savedMapSelectionGeneration &&
    selectedSavedMapId === meta.id &&
    String(selectedSavedMapMeta?.revision || '') === expectedRevision
  );
  if (switchingEditorSource) detachMapEditor(meta.kind === 'occupancy2d' ? '2D 지도 데이터를 불러오고 있습니다.' : '편집하려면 저장된 2D 지도를 선택하세요.');
  selectedSavedMapId = meta.id;
  selectedSavedMapMeta = meta;
  savedMapViewPreference = meta.kind === 'occupancy2d' ? 'occupancy' : 'cloud';
  ui.savedMapViewMode.value = savedMapViewPreference;
  if (meta.kind === 'occupancy2d') savedOccupancySnapshot = null;
  else offlineCloudSnapshot = null;
  updateSavedMapOverview();
  try {
    const cacheKey = pointBudgetCacheKey(meta.id, savedPointLimit, meta.kind, meta.revision);
    let payload = savedMapDataCache.get(cacheKey);
    if (!payload) {
      let pending = savedMapLoadPromises.get(cacheKey);
      if (!pending) {
        pending = api(meta.kind === 'pointcloud3d' ? savedPointDataUrl(meta) : (meta.data_url || `/api/v1/saved-maps/${encodeURIComponent(meta.id)}/data`));
        savedMapLoadPromises.set(cacheKey, pending);
      }
      try {
        payload = await pending;
      } finally {
        if (savedMapLoadPromises.get(cacheKey) === pending) savedMapLoadPromises.delete(cacheKey);
      }
      if (!loadIsCurrent()) return false;
      if (expectedRevision && String(payload?.revision || '') !== expectedRevision) {
        throw new Error('지도를 불러오는 동안 revision이 변경됐습니다. 목록을 새로고침한 뒤 다시 선택하세요.');
      }
      savedMapDataCache.set(cacheKey, payload);
      while (savedMapDataCache.size > 2) {
        savedMapDataCache.delete(savedMapDataCache.keys().next().value);
      }
    }
    if (!loadIsCurrent()) return false;
    if (expectedRevision && String(payload?.revision || '') !== expectedRevision) {
      savedMapDataCache.delete(cacheKey);
      throw new Error('캐시된 지도 revision이 현재 목록과 다릅니다. 지도를 다시 선택하세요.');
    }
    if (meta.kind === 'occupancy2d') {
      savedOccupancySnapshot = payload;
      initializeMapEditor(meta, payload);
    } else {
      offlineCloudSnapshot = { ...payload, offline_snapshot: true };
      if (!mapEditorSession || mapEditorSession.sourceId !== meta.id) detachMapEditor('편집하려면 저장된 2D 지도를 선택하세요.');
    }
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    if (notify) showToast(`${meta.name || '저장 지도'}를 불러왔습니다.`);
    return true;
  } catch (error) {
    if (!loadIsCurrent()) return false;
    setStatePill(ui.savedMappingState, 'error', 'LOAD FAILED');
    if (notify) showToast(`저장 지도 로드 실패: ${error.message}`, true);
    if (rethrow) throw error;
    return false;
  }
}

function clearSavedMapCache(mapId) {
  for (const key of savedMapDataCache.keys()) {
    if (key.startsWith(`${mapId}:`)) savedMapDataCache.delete(key);
  }
  for (const key of savedMapLoadPromises.keys()) {
    if (key.startsWith(`${mapId}:`)) savedMapLoadPromises.delete(key);
  }
}

async function renameSelectedSavedMap() {
  if (savedMapMutationBusy || editorHasUnsavedChanges() || mapConversionPending || mapEditorBusy || !selectedSavedMapMeta?.manageable) return;
  const name = ui.savedMapNameInput.value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name)) {
    showToast('지도 이름은 영문·숫자로 시작하고 영문·숫자·_·-만 사용할 수 있습니다.', true);
    return;
  }
  if (name === selectedSavedMapMeta.name) {
    showToast('현재 이름과 같습니다.');
    return;
  }
  const previousId = selectedSavedMapId;
  savedMapMutationBusy = true;
  updateSavedMapManagement();
  try {
    const result = await api(`/api/v1/saved-maps/${encodeURIComponent(previousId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
    clearSavedMapCache(previousId);
    selectedSavedMapId = result.map.id;
    selectedSavedMapMeta = result.map;
    if (result.map.kind === 'pointcloud3d') offlineCloudSnapshot = null;
    else savedOccupancySnapshot = null;
    await refreshSavedMaps();
    showToast(`${result.map.name}으로 이름을 변경했습니다.`);
  } catch (error) {
    showToast(`이름 변경 실패: ${error.message}`, true);
  } finally {
    savedMapMutationBusy = false;
    updateSavedMapManagement();
  }
}

async function deleteSelectedSavedMap() {
  if (savedMapMutationBusy || editorHasUnsavedChanges() || mapConversionPending || mapEditorBusy || !selectedSavedMapMeta?.manageable) return;
  const selected = selectedSavedMapMeta;
  const paired = selected.kind === 'occupancy2d' ? ' (YAML과 PGM 모두)' : '';
  if (!window.confirm(`${selected.name}${paired}을 삭제할까요? 이 작업은 되돌릴 수 없습니다.`)) return;
  const previousId = selectedSavedMapId;
  savedMapMutationBusy = true;
  updateSavedMapManagement();
  try {
    await api(`/api/v1/saved-maps/${encodeURIComponent(previousId)}`, { method: 'DELETE' });
    clearSavedMapCache(previousId);
    if (selected.kind === 'pointcloud3d') offlineCloudSnapshot = null;
    else savedOccupancySnapshot = null;
    selectedSavedMapId = '';
    selectedSavedMapMeta = null;
    await refreshSavedMaps();
    showToast(`${selected.name} 지도를 삭제했습니다.`);
  } catch (error) {
    showToast(`지도 삭제 실패: ${error.message}`, true);
  } finally {
    savedMapMutationBusy = false;
    updateSavedMapManagement();
  }
}

function setMapLayerVisibility(mode) {
  const cloudMode = mode === 'cloud';
  const projectionMode = mode === 'projection';
  const occupancyMode = mode === 'occupancy';
  ui.sceneCanvas?.classList.toggle('is-hidden', !cloudMode);
  ui.liveMap2dCanvas?.classList.toggle('is-hidden', !projectionMode);
  ui.mapCanvas?.classList.toggle('is-hidden', !occupancyMode);
  ui.mapGridOverlay?.classList.toggle('is-hidden', !occupancyMode);
  ui.sceneControls?.classList.toggle('is-hidden', !cloudMode);
  ui.liveMap2dControls?.classList.toggle('is-hidden', !projectionMode);
  ui.liveProjectionLegend?.classList.toggle('is-hidden', !projectionMode);
  if (cloudMode) scene3d?.resize();
  if (projectionMode) liveMap2d?.resize();
}

function setSavedMapLayerVisibility(mode) {
  const cloudMode = mode !== 'occupancy';
  ui.savedSceneCanvas?.classList.toggle('is-hidden', !cloudMode);
  ui.savedMapCanvas?.classList.toggle('is-hidden', cloudMode);
  ui.savedMapGridOverlay?.classList.toggle('is-hidden', cloudMode);
  ui.savedSceneControls?.classList.toggle('is-hidden', !cloudMode);
  if (cloudMode) savedScene3d?.resize();
}

function drawPointcloud(cloud) {
  const selectedCloud = liveSceneCloud(cloud);
  setMapLayerVisibility('cloud');
  activeMapView = 'cloud';
  if (!scene3d) return;
  if (!selectedCloud?.points?.length) {
    if (liveSceneHadCloud) {
      scene3d.clearPointCloud();
      sceneCloudDataKey = '';
      sceneCloudSourceKey = '';
      liveSceneHadCloud = false;
    }
    scene3d.setRobotPose(null);
    scene3d.setTrail([]);
    scene3d.setRobotVisible(mapOverlayVisible && robotRuntimeDataCompatible);
    scene3d.setStatus({
      online: Boolean(latestState?.health?.robot_online),
      lidarOnline: false,
      snapshot: false,
      message: robotRuntimeDataCompatible
        ? '실시간 LiDAR 신호를 기다리고 있습니다'
        : 'ROS 재시작 전 로봇 오버레이 숨김',
    });
    return;
  }

  const sourceKey = `live:${selectedCloud.topic || selectedCloud.frame_id || 'cloud'}`;
  const dataKey = `${sourceKey}:${selectedCloud.seq ?? selectedCloud.stamp_ns ?? cloudPointCount(selectedCloud)}`;
  if (dataKey !== sceneCloudDataKey) {
    scene3d.setPointCloud(selectedCloud, { fit: sourceKey !== sceneCloudSourceKey });
    sceneCloudDataKey = dataKey;
    sceneCloudSourceKey = sourceKey;
  }
  liveSceneHadCloud = true;
  scene3d.setRobotPose(robotRuntimeDataCompatible && poseLive ? currentPose : null);
  scene3d.setTrail(robotRuntimeDataCompatible ? poseTrail : []);
  scene3d.setRobotVisible(mapOverlayVisible && robotRuntimeDataCompatible);
  scene3d.setTrailVisible(mapOverlayVisible && robotRuntimeDataCompatible);
  scene3d.setStatus({
    online: poseLive || jointLive || Boolean(latestState?.health?.robot_online),
    lidarOnline: isLiveCloudReady(),
    snapshot: false,
    message: robotRuntimeDataCompatible
      ? '실시간 LiDAR 포인트클라우드'
      : 'ROS 재시작 전 기존 데이터 · 로봇 오버레이 숨김',
  });
}

function drawLivePointProjection(cloud) {
  const selectedCloud = liveSceneCloud(cloud);
  setMapLayerVisibility('projection');
  activeMapView = 'projection';
  if (!liveMap2d) return;
  liveMap2d.setOverlayVisible(mapOverlayVisible && robotRuntimeDataCompatible);
  liveMap2d.setPose(robotRuntimeDataCompatible && poseLive ? currentPose : null);
  liveMap2d.setTrail(robotRuntimeDataCompatible ? poseTrail : []);
  if (!selectedCloud?.points?.length) {
    if (liveMap2dDataKey) liveMap2d.clearPointCloud();
    liveMap2dDataKey = '';
    liveMap2dSourceKey = '';
    return;
  }
  const sourceKey = `live:${selectedCloud.topic || selectedCloud.frame_id || 'cloud'}`;
  const dataKey = `${sourceKey}:${selectedCloud.seq ?? selectedCloud.stamp_ns ?? cloudPointCount(selectedCloud)}`;
  if (dataKey !== liveMap2dDataKey) {
    liveMap2d.setPointCloud(selectedCloud, { fit: sourceKey !== liveMap2dSourceKey });
    liveMap2dDataKey = dataKey;
    liveMap2dSourceKey = sourceKey;
  }
}

function drawSavedPointcloud() {
  const selectedCloud = savedSceneCloud();
  setSavedMapLayerVisibility('cloud');
  if (!savedScene3d) return;
  if (!selectedCloud?.points?.length) {
    savedScene3d.clearPointCloud();
    savedScene3d.setRobotPose(null);
    savedScene3d.setStatus({ online: null, lidarOnline: null, snapshot: true, message: '저장된 3D 지도가 없습니다' });
    return;
  }
  const sourceKey = `saved:${selectedSavedMapId || selectedCloud.map_id || 'fallback'}:${selectedCloud.topic || selectedCloud.frame_id || 'cloud'}`;
  const dataKey = `${sourceKey}:${selectedCloud.seq ?? cloudPointCount(selectedCloud)}`;
  if (dataKey !== savedSceneCloudDataKey) {
    savedScene3d.setPointCloud(selectedCloud, { fit: sourceKey !== savedSceneCloudSourceKey });
    savedSceneCloudDataKey = dataKey;
    savedSceneCloudSourceKey = sourceKey;
  }
  savedScene3d.setRobotPose(null);
  savedScene3d.setTrail([]);
  savedScene3d.setRobotVisible(savedMapOverlayVisible);
  savedScene3d.setTrailVisible(false);
  savedScene3d.setStatus({ online: null, lidarOnline: null, snapshot: true, message: selectedCloud.demo_snapshot ? '공개용 데모 지도' : '저장된 LiDAR 지도' });
}

async function refreshMap() {
  try {
    const map = await latestApi('/api/v1/map', mapSeq);
    if (!map?.seq || !map.data_b64) return;
    mapSeq = map.seq;
    lastMapSnapshot = map;
    if (activePage === 'mapping' && desiredMapView() === 'occupancy') drawOccupancyMap(map, false);
    syncPointcloudTransport();
  } catch (_) {}
}

function drawOccupancyMap(map, saved = false) {
  if (saved) setSavedMapLayerVisibility('occupancy'); else setMapLayerVisibility('occupancy');
  const canvas = saved ? ui.savedMapCanvas : ui.mapCanvas;
  const { width, height, ratio } = resizeCanvas(canvas);
  const source = document.createElement('canvas');
  source.width = map.width; source.height = map.height;
  const sourceContext = source.getContext('2d');
  const image = sourceContext.createImageData(map.width, map.height);
  const binary = atob(map.data_b64);
  for (let y = 0; y < map.height; y++) {
    for (let x = 0; x < map.width; x++) {
      const inputIndex = y * map.width + x;
      const outputIndex = ((map.height - 1 - y) * map.width + x) * 4;
      const raw = binary.charCodeAt(inputIndex);
      const value = raw > 127 ? -1 : raw;
      const shade = value < 0 ? 35 : value >= 65 ? 7 : 205;
      image.data[outputIndex] = shade * .55;
      image.data[outputIndex + 1] = shade;
      image.data[outputIndex + 2] = shade * .82;
      image.data[outputIndex + 3] = 255;
    }
  }
  sourceContext.putImageData(image, 0, 0);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#06100e'; ctx.fillRect(0, 0, width, height);
  const scale = Math.min(width / map.width, height / map.height) * .94;
  const drawWidth = map.width * scale, drawHeight = map.height * scale;
  const left = (width - drawWidth) / 2;
  const top = (height - drawHeight) / 2;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(source, left, top, drawWidth, drawHeight);
  if (saved) savedOccupancySnapshot = map;
  else {
    lastMapSnapshot = map;
    activeMapView = 'occupancy';
  }
  const origin = Array.isArray(map.origin) ? map.origin : [0, 0, 0];
  const originX = Number(origin[0]) || 0;
  const originY = Number(origin[1]) || 0;
  const originYaw = Number(origin[2]) || 0;
  const resolution = Math.max(Number(map.resolution) || 0, 0.0001);
  const cos = Math.cos(originYaw);
  const sin = Math.sin(originYaw);
  const projectWorld = (pose) => {
    const dx = pose.x - originX;
    const dy = pose.y - originY;
    const localX = cos * dx + sin * dy;
    const localY = -sin * dx + cos * dy;
    return {
      x: left + (localX / resolution) * scale,
      y: top + drawHeight - (localY / resolution) * scale,
      heading: -(pose.yaw - originYaw),
      inside: localX >= 0 && localX <= map.width * resolution && localY >= 0 && localY <= map.height * resolution,
    };
  };
  if (!saved) drawMapOverlay(ctx, { width, height, ratio, projectWorld, fallbackScale: scale / resolution, mode: 'GRID', frameId: map.frame_id || '' });
}

function extractNavigationSnapshot(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.navigation && typeof payload.navigation === 'object') return payload.navigation;
  if (payload.pipeline && payload.readiness && payload.goal) return payload;
  return null;
}

function navigationActivityBlocksManualControl() {
  return Boolean(
    navigationEngine &&
    (navigationEngine.pipelineActive(navigationSnapshot) || navigationEngine.goalActive(navigationSnapshot))
  );
}

function navigationManualControlConflict() {
  return Boolean(
    controlArmBusy ||
    navigationEngine?.manualControlActive(controlSnapshot, controlLeaseId)
  );
}

function navigationMapCandidates() {
  return savedMapCatalog.filter((entry) => (
    entry.kind === 'occupancy2d' &&
    entry.format === 'map-server-pgm' &&
    typeof entry.revision === 'string' &&
    entry.revision.length > 0
  ));
}

function navigationActiveMapMatchesSelection() {
  if (!navigationEngine?.pipelineActive(navigationSnapshot)) return true;
  const active = navigationSnapshot?.map || {};
  const activeId = String(active.id || '');
  const activeRevision = String(active.revision || '');
  return Boolean(
    activeId &&
    activeRevision &&
    navigationSelectedMapMeta?.id === activeId &&
    String(navigationSelectedMapMeta?.revision || '') === activeRevision &&
    String(navigationMapSnapshot?.revision || '') === activeRevision &&
    navigationMapCandidates().some((entry) => entry.id === activeId && String(entry.revision || '') === activeRevision)
  );
}

async function syncNavigationMapOptions() {
  const candidates = navigationMapCandidates();
  const previousId = navigationSelectedMapMeta?.id || ui.navigationMapSelect.value;
  const activeMapId = String(navigationSnapshot?.map?.id || '');
  const activeMapRevision = String(navigationSnapshot?.map?.revision || '');
  const pipelineActive = navigationEngine?.pipelineActive(navigationSnapshot) || false;
  const exactActiveMap = candidates.find((entry) => entry.id === activeMapId && String(entry.revision || '') === activeMapRevision);
  if (pipelineActive && !exactActiveMap) {
    ui.navigationMapSelect.innerHTML = `<option value="${escapeHtml(activeMapId)}">활성 지도 revision 확인 필요</option>`;
    ui.navigationMapSelect.value = activeMapId;
    navigationMapError = '활성 Nav2 지도 ID·revision이 현재 Saved Maps catalog와 일치하지 않습니다. STOP 후 지도를 다시 선택하세요.';
    discardNavigationPose(false);
    drawNavigationMap();
    renderNavigationStatus();
    return false;
  }
  const savedSelection = selectedSavedMapMeta?.kind === 'occupancy2d' ? selectedSavedMapId : '';
  ui.navigationMapSelect.innerHTML = candidates.length
    ? candidates.map((entry) => `<option value="${escapeHtml(entry.id)}">${escapeHtml(entry.name || entry.file_name || 'Saved 2D map')}</option>`).join('')
    : '<option value="">저장된 2D 지도 없음</option>';
  const preferredId = [
    pipelineActive ? activeMapId : '',
    previousId,
    savedSelection,
    candidates[0]?.id || '',
  ].find((id) => candidates.some((entry) => entry.id === id)) || '';
  ui.navigationMapSelect.value = preferredId;
  const selected = candidates.find((entry) => entry.id === preferredId) || null;
  if (!selected) {
    navigationMapLoadGeneration += 1;
    navigationSelectedMapMeta = null;
    navigationMapSnapshot = null;
    navigationMapSourceCanvas = null;
    navigationMapCells = null;
    navigationMapLayout = null;
    navigationMapError = candidates.length ? '선택한 정적 지도를 찾을 수 없습니다.' : 'Saved Maps에 2D YAML·PGM 지도가 없습니다.';
    resetMapAnnotations(navigationMapError);
    discardNavigationPose(false);
    drawNavigationMap();
    renderNavigationStatus();
    return false;
  }
  if (
    navigationSelectedMapMeta?.id === selected.id &&
    navigationSelectedMapMeta?.revision === selected.revision &&
    navigationMapSnapshot?.revision === selected.revision &&
    navigationMapSourceCanvas
  ) {
    navigationSelectedMapMeta = selected;
    drawNavigationMap();
    renderNavigationStatus();
    return true;
  }
  return loadNavigationMap(selected);
}

function buildNavigationMapSource(map) {
  const geometry = navigationEngine.mapGeometry(map);
  const binary = atob(String(map.data_b64 || ''));
  if (binary.length !== geometry.width * geometry.height) throw new Error('2D 지도 셀 수가 width·height와 일치하지 않습니다.');
  const source = document.createElement('canvas');
  source.width = geometry.width;
  source.height = geometry.height;
  const context = source.getContext('2d');
  const image = context.createImageData(geometry.width, geometry.height);
  const cells = new Int8Array(geometry.width * geometry.height);
  for (let y = 0; y < geometry.height; y += 1) {
    for (let x = 0; x < geometry.width; x += 1) {
      const input = y * geometry.width + x;
      const output = ((geometry.height - 1 - y) * geometry.width + x) * 4;
      const byte = binary.charCodeAt(input);
      const value = byte > 127 ? byte - 256 : byte;
      cells[input] = value;
      const color = value < 0 ? [30, 45, 41] : value >= 65 ? [8, 13, 12] : [185, 220, 207];
      image.data[output] = color[0];
      image.data[output + 1] = color[1];
      image.data[output + 2] = color[2];
      image.data[output + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
  return { source, cells };
}

function resetMapAnnotations(message = '저장된 2D 지도를 선택하세요.') {
  mapAnnotationFeature?.reset(message);
}

async function loadMapAnnotations(meta, mapGeneration) {
  return mapAnnotationFeature?.load(meta, mapGeneration) || false;
}

async function loadNavigationMap(meta) {
  if (!meta || !navigationEngine) return false;
  const generation = ++navigationMapLoadGeneration;
  navigationSelectedMapMeta = meta;
  navigationMapSnapshot = null;
  navigationMapSourceCanvas = null;
  navigationMapCells = null;
  navigationMapLayout = null;
  navigationMapError = '';
  resetMapAnnotations('지도 데이터를 불러오는 중입니다.');
  discardNavigationPose(false);
  ui.navigationMapSelect.value = meta.id;
  setStatePill(ui.navigationMapState, 'waiting', 'LOADING');
  drawNavigationMap();
  renderNavigationStatus();
  try {
    const payload = await api(meta.data_url || `/api/v1/saved-maps/${encodeURIComponent(meta.id)}/data`);
    if (generation !== navigationMapLoadGeneration || navigationSelectedMapMeta?.id !== meta.id) return false;
    if (String(payload?.revision || '') !== String(meta.revision || '')) {
      throw new Error('지도 revision이 목록과 다릅니다. Saved Maps 목록을 새로고침하세요.');
    }
    navigationEngine.mapGeometry(payload);
    const decoded = buildNavigationMapSource(payload);
    navigationMapSourceCanvas = decoded.source;
    navigationMapCells = decoded.cells;
    navigationMapSnapshot = payload;
    navigationMapError = '';
    await loadMapAnnotations(meta, generation);
    drawNavigationMap();
    renderNavigationStatus();
    return true;
  } catch (error) {
    if (generation !== navigationMapLoadGeneration || navigationSelectedMapMeta?.id !== meta.id) return false;
    navigationMapError = error.message;
    navigationMapSnapshot = null;
    navigationMapSourceCanvas = null;
    navigationMapCells = null;
    setStatePill(ui.navigationMapState, 'error', 'LOAD FAILED');
    drawNavigationMap();
    renderNavigationStatus();
    return false;
  }
}

function drawNavigationPoseMarker(context, layout, pose, color, label, ratio = 1, dashed = false) {
  if (!pose || !navigationEngine) return;
  let projected;
  try { projected = navigationEngine.worldToCanvas(layout, pose); }
  catch (_) { return; }
  if (!projected.inside) return;
  const radius = 6 * ratio;
  const arrow = 28 * ratio;
  context.save();
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineWidth = 2 * ratio;
  if (dashed) context.setLineDash([5 * ratio, 4 * ratio]);
  context.beginPath();
  context.arc(projected.x, projected.y, radius, 0, Math.PI * 2);
  context.stroke();
  const tipX = projected.x + Math.cos(projected.heading) * arrow;
  const tipY = projected.y + Math.sin(projected.heading) * arrow;
  context.beginPath();
  context.moveTo(projected.x, projected.y);
  context.lineTo(tipX, tipY);
  context.stroke();
  context.setLineDash([]);
  context.beginPath();
  context.arc(tipX, tipY, 2.5 * ratio, 0, Math.PI * 2);
  context.fill();
  context.font = `${Math.max(8, 8 * ratio)}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  context.fillText(label, projected.x + 9 * ratio, projected.y - 9 * ratio);
  context.restore();
}

function drawNavigationMap() {
  if (!ui.navigationMapCanvas) return;
  const canvas = ui.navigationMapCanvas;
  const { width, height, ratio } = resizeCanvas(canvas);
  const context = canvas.getContext('2d');
  context.fillStyle = '#04100d';
  context.fillRect(0, 0, width, height);
  const ready = Boolean(navigationEngine && navigationMapSnapshot && navigationMapSourceCanvas);
  ui.navigationMapEmpty.hidden = ready;
  if (!ready) {
    navigationMapLayout = null;
    if (navigationMapError) {
      ui.navigationMapEmpty.innerHTML = `<strong>MAP UNAVAILABLE</strong><small>${escapeHtml(navigationMapError)}</small>`;
    } else {
      ui.navigationMapEmpty.innerHTML = '<strong>STATIC MAP REQUIRED</strong><small>Saved Maps에서 2D YAML·PGM 지도를 준비하세요.</small>';
    }
    return;
  }
  try {
    const layout = navigationEngine.mapLayout(navigationMapSnapshot, width, height, 0.055);
    navigationMapLayout = layout;
    context.imageSmoothingEnabled = false;
    context.drawImage(navigationMapSourceCanvas, layout.left, layout.top, layout.drawWidth, layout.drawHeight);
    context.strokeStyle = 'rgba(93,222,216,.34)';
    context.lineWidth = Math.max(1, ratio);
    context.strokeRect(layout.left, layout.top, layout.drawWidth, layout.drawHeight);
    mapAnnotationFeature?.draw(context, layout, ratio);

    const path = Array.isArray(navigationSnapshot?.path) ? navigationSnapshot.path : [];
    const projectedPath = path.map((pose) => {
      try { return navigationEngine.worldToCanvas(layout, pose); } catch (_) { return null; }
    }).filter((point) => point?.inside);
    if (projectedPath.length > 1) {
      context.save();
      context.beginPath();
      projectedPath.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
      context.strokeStyle = 'rgba(162,139,255,.88)';
      context.lineWidth = 2 * ratio;
      context.setLineDash([6 * ratio, 4 * ratio]);
      context.stroke();
      context.restore();
    }
    drawNavigationPoseMarker(context, layout, navigationSnapshot?.localization?.pose, '#7df0b6', 'ROBOT', ratio);
    drawNavigationPoseMarker(context, layout, navigationSnapshot?.goal?.pose, '#a28bff', 'GOAL', ratio, true);
    if (navigationStagedPose) {
      drawNavigationPoseMarker(
        context,
        layout,
        navigationStagedPose,
        navigationStagedPose.mode === 'initial' ? '#5dded8' : '#ffc66d',
        navigationStagedPose.mode === 'initial' ? 'INITIAL · STAGED' : 'GOAL · STAGED',
        ratio,
      );
    }
  } catch (error) {
    navigationMapLayout = null;
    navigationMapError = error.message;
    ui.navigationMapEmpty.hidden = false;
    ui.navigationMapEmpty.innerHTML = `<strong>MAP RENDER FAILED</strong><small>${escapeHtml(error.message)}</small>`;
  }
}

function scheduleNavigationMapDraw() {
  if (navigationRenderFrame) return;
  navigationRenderFrame = requestAnimationFrame(() => {
    navigationRenderFrame = 0;
    drawNavigationMap();
  });
}

function navigationCanvasPoint(event) {
  const bounds = ui.navigationMapCanvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return null;
  return {
    x: (event.clientX - bounds.left) * (ui.navigationMapCanvas.width / bounds.width),
    y: (event.clientY - bounds.top) * (ui.navigationMapCanvas.height / bounds.height),
  };
}

function navigationPoseToolAllowed(mode) {
  const state = String(navigationSnapshot?.pipeline?.state || '').toLowerCase();
  const robotOnline = navigationSnapshot?.robot_online === true;
  const manualConflict = navigationManualControlConflict();
  const safety = navigationSnapshot?.safety || {};
  if (!navigationApiAvailable || state !== 'running' || !robotOnline || manualConflict || !navigationMapSnapshot || !navigationActiveMapMatchesSelection()) return false;
  if (mode === 'initial') return safety.can_set_initial_pose === true;
  return safety.can_send_goal === true &&
    String(navigationSnapshot?.localization?.state || '').toLowerCase() === 'localized' &&
    !navigationEngine?.goalActive(navigationSnapshot);
}

function renderNavigationPoseSelection() {
  const initialAllowed = navigationPoseToolAllowed('initial');
  const goalAllowed = navigationPoseToolAllowed('goal');
  ui.navigationInitialPoseTool.disabled = navigationOperationBusy || !initialAllowed;
  ui.navigationGoalPoseTool.disabled = navigationOperationBusy || !goalAllowed;
  ui.navigationInitialPoseTool.classList.toggle('is-active', navigationMapTool === 'initial');
  ui.navigationGoalPoseTool.classList.toggle('is-active', navigationMapTool === 'goal');
  ui.navigationInitialPoseTool.setAttribute('aria-pressed', navigationMapTool === 'initial' ? 'true' : 'false');
  ui.navigationGoalPoseTool.setAttribute('aria-pressed', navigationMapTool === 'goal' ? 'true' : 'false');
  const staged = navigationStagedPose;
  ui.navigationPoseMode.textContent = staged
    ? `${staged.mode === 'initial' ? 'INITIAL' : 'GOAL'} · STAGED`
    : navigationMapTool ? `${navigationMapTool === 'initial' ? 'INITIAL' : 'GOAL'} · DRAW ON MAP` : 'NO TOOL';
  ui.navigationPoseCoordinates.textContent = staged
    ? `X ${staged.x.toFixed(3)} · Y ${staged.y.toFixed(3)} · YAW ${staged.yaw.toFixed(3)}`
    : 'X — · Y — · YAW —';
  const stagedAllowed = staged && navigationPoseToolAllowed(staged.mode);
  ui.navigationPoseDiscard.disabled = !staged || navigationOperationBusy;
  ui.navigationPoseSend.disabled = !stagedAllowed || navigationOperationBusy;
  ui.navigationPoseSend.textContent = staged?.mode === 'goal' ? 'SEND GOAL' : 'SEND POSE';
}

function discardNavigationPose(render = true) {
  navigationPointer = null;
  navigationStagedPose = null;
  ui.navigationMapCanvas?.classList.remove('is-dragging');
  if (render) {
    renderNavigationPoseSelection();
    drawNavigationMap();
  }
}

function selectNavigationTool(mode) {
  const normalized = mode === 'goal' ? 'goal' : 'initial';
  if (!navigationPoseToolAllowed(normalized)) {
    showToast(normalized === 'goal' ? '목표 전송 조건이 준비되지 않았습니다.' : '초기 위치 지정 조건이 준비되지 않았습니다.', true);
    return;
  }
  mapAnnotationFeature?.cancelDrawing({ render: false });
  navigationMapTool = navigationMapTool === normalized ? '' : normalized;
  navigationStagedPose = null;
  renderNavigationPoseSelection();
  drawNavigationMap();
}

function beginNavigationPose(event) {
  const canvasPoint = navigationCanvasPoint(event);
  if (mapAnnotationFeature?.beginPointer(event, canvasPoint)) return;
  if (event.button !== 0 || !navigationMapTool || navigationOperationBusy || !navigationMapLayout) return;
  if (!navigationPoseToolAllowed(navigationMapTool)) return;
  const point = navigationCanvasPoint(event);
  let occupancy = null;
  try {
    occupancy = point && navigationEngine.occupancyCellAtCanvas(navigationMapLayout, navigationMapCells, point);
  } catch (_) {}
  if (!occupancy?.inside) {
    ui.navigationMapHint.textContent = '지도 경계 안에서 위치를 선택하세요.';
    ui.navigationMapHint.classList.add('is-error');
    return;
  }
  if (!occupancy.free) {
    ui.navigationMapHint.textContent = occupancy.value < 0
      ? '미관측(UNKNOWN) 셀에는 위치나 목표를 지정할 수 없습니다.'
      : '장애물(OCCUPIED) 셀에는 위치나 목표를 지정할 수 없습니다.';
    ui.navigationMapHint.classList.add('is-error');
    return;
  }
  event.preventDefault();
  ui.navigationMapHint.classList.remove('is-error');
  ui.navigationMapHint.textContent = '진행 방향으로 드래그한 뒤 SEND 버튼으로 확인하세요.';
  try { ui.navigationMapCanvas.setPointerCapture(event.pointerId); } catch (_) {}
  navigationPointer = { id: event.pointerId, start: point, end: point, mode: navigationMapTool };
  ui.navigationMapCanvas.classList.add('is-dragging');
  updateNavigationStagedPose();
}

function updateNavigationStagedPose() {
  if (!navigationPointer || !navigationMapLayout) return;
  const fallbackYaw = Number(navigationSnapshot?.localization?.pose?.yaw) || 0;
  const pose = navigationEngine.poseFromDrag(
    navigationMapLayout,
    navigationPointer.start,
    navigationPointer.end,
    fallbackYaw,
  );
  navigationStagedPose = pose ? { mode: navigationPointer.mode, ...pose } : null;
  renderNavigationPoseSelection();
  scheduleNavigationMapDraw();
}

function moveNavigationPose(event) {
  if (mapAnnotationFeature?.movePointer(event, navigationCanvasPoint(event))) return;
  if (!navigationPointer || navigationPointer.id !== event.pointerId) return;
  const point = navigationCanvasPoint(event);
  if (!point) return;
  event.preventDefault();
  navigationPointer.end = point;
  updateNavigationStagedPose();
}

function finishNavigationPose(event) {
  if (mapAnnotationFeature?.finishPointer(event, navigationCanvasPoint(event))) return;
  if (!navigationPointer || navigationPointer.id !== event.pointerId) return;
  const point = navigationCanvasPoint(event);
  if (point) navigationPointer.end = point;
  updateNavigationStagedPose();
  navigationPointer = null;
  ui.navigationMapCanvas.classList.remove('is-dragging');
  try { ui.navigationMapCanvas.releasePointerCapture(event.pointerId); } catch (_) {}
  renderNavigationPoseSelection();
}

function navigationStatusCard(strong, note, state, label, message) {
  const card = strong.closest('.navigation-status-card');
  card?.classList.toggle('is-ok', state === 'ok');
  card?.classList.toggle('is-error', state === 'error');
  strong.textContent = label;
  note.textContent = message;
}

function navigationStartupPresentation(snapshot) {
  const dependency = snapshot?.localization_pipeline;
  if (!dependency || typeof dependency !== 'object') return null;
  const phase = String(dependency.phase || '').toLowerCase();
  const presentation = NAVIGATION_STARTUP_PHASES[phase];
  if (!presentation) return null;
  const error = typeof dependency.error === 'string' ? dependency.error.trim().slice(0, 160) : '';
  return {
    phase,
    label: presentation.label,
    message: error || presentation.message,
    tone: presentation.tone,
    pending: dependency.pending === true,
    ownedByNavigation: dependency.owned_by_navigation === true,
  };
}

function navigationBlockerMessage(blocker) {
  const messages = {
    navigation_unavailable: 'Nav2 패키지 또는 허용된 launcher가 준비되지 않았습니다.',
    robot_offline: '로봇 연결이 없어 새 주행 명령을 보낼 수 없습니다.',
    manual_control_active: '수동 제어가 ARM되어 있습니다. Controls에서 먼저 DISARM하세요.',
    mapping_active: '공유 위치추정 파이프라인이 이미 실행 중입니다. Navigation이 이 센서 파이프라인을 재사용합니다.',
    mapping_transition: '공유 위치추정 파이프라인이 전환 중입니다. 잠시 기다리거나 STOP으로 시작 작업을 정리하세요.',
    mapping_operation_active: '지도 저장·변환 작업이 끝난 뒤 Nav2를 시작할 수 있습니다.',
    navigation_transition: 'Navigation 시작 또는 중지 작업이 진행 중입니다.',
    localization_pipeline_not_running: '공유 위치추정 센서 파이프라인을 준비하지 못했습니다. Navigation 로그를 확인하세요.',
    map_required: '정적 2D 지도를 선택하세요.',
    initial_pose_required: '지도에서 로봇의 초기 위치와 방향을 지정하세요.',
    localization_lost: '위치추정이 유실되었습니다. 초기 위치를 다시 지정하세요.',
    parameters_unavailable: '안전한 파라미터 snapshot이 없습니다.',
  };
  return messages[String(blocker || '')] || String(blocker || '').replaceAll('_', ' ');
}

function formatNavigationMetric(value, suffix = '', digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(digits)}${suffix}` : '—';
}

function renderNavigationHealth(snapshot) {
  const health = snapshot?.localization_health;
  const metrics = health?.metrics;
  const state = String(health?.state || 'UNAVAILABLE').toUpperCase();
  const tone = state === 'READY' ? 'ok' : ['STALE', 'DISCONTINUITY', 'FRAME_MISMATCH', 'CALIBRATION_SUSPECTED'].includes(state) ? 'error' : 'waiting';
  setStatePill(ui.navigationHealthState, tone, state);
  const reasonCode = String(health?.reason_code || 'TELEMETRY_UNAVAILABLE');
  const basis = String(health?.threshold_basis || 'Navigation runtime telemetry를 기다리고 있습니다.');
  ui.navigationHealthReason.textContent = `${reasonCode} · ${basis}`.slice(0, 240);

  const rows = [
    ['POINTCLOUD', formatNavigationMetric(metrics?.cloud_frequency_hz, ' Hz'), `jitter ${formatNavigationMetric(metrics?.cloud_jitter_s, ' s', 3)} · age ${formatNavigationMetric(metrics?.cloud_age_s, ' s', 3)} · health ${formatNavigationMetric(metrics?.runtime_health_age_s, ' s', 3)}`],
    ['ODOMETRY', formatNavigationMetric(metrics?.odometry_frequency_hz, ' Hz'), `jitter ${formatNavigationMetric(metrics?.odometry_jitter_s, ' s', 3)} · age ${formatNavigationMetric(metrics?.odometry_age_s, ' s', 3)}`],
    ['TF AGE', formatNavigationMetric(metrics?.tf_age_s, ' s', 3), `map→odom ${formatNavigationMetric(metrics?.map_to_odom_age_s, ' s', 3)} · odom→base ${formatNavigationMetric(metrics?.odom_to_base_age_s, ' s', 3)}`],
    ['FAST-LIO JUMPS', `${Number(metrics?.translation_jump_count) || 0} / ${Number(metrics?.heading_jump_count) || 0}`, 'translation / heading'],
    ['SCAN POINTS', `${Number(metrics?.accepted_points) || 0} / ${Number(metrics?.input_points) || 0}`, 'accepted / input'],
    ['GOAL PROGRESS', formatNavigationMetric(metrics?.goal_progress_rate_mps, ' m/s', 3), `remaining ${formatNavigationMetric(metrics?.goal_remaining_distance_m, ' m')} · stall ${formatNavigationMetric(metrics?.controller_stall_duration_s, ' s')}`],
    ['COSTMAP CLEARS', String(Number(metrics?.costmap_clear_count) || 0), `fresh sequence ${Number(metrics?.fresh_sequence_count) || 0}`],
  ];
  ui.navigationHealthMetrics.replaceChildren(...rows.map(([label, value, note]) => {
    const row = document.createElement('div');
    const span = document.createElement('span');
    const strong = document.createElement('strong');
    const small = document.createElement('small');
    span.textContent = label;
    strong.textContent = value;
    small.textContent = note;
    row.append(span, strong, small);
    return row;
  }));

  const assistant = snapshot?.calibration_assistant;
  const items = Array.isArray(assistant?.items) ? assistant.items.slice(0, 8) : [];
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'sensor-placeholder';
    empty.textContent = '고정 frame·clock·extrinsic 계약을 확인하고 있습니다.';
    ui.navigationCalibrationList.replaceChildren(empty);
    return;
  }
  ui.navigationCalibrationList.replaceChildren(...items.map((entry) => {
    const card = document.createElement('article');
    const head = document.createElement('div');
    const code = document.createElement('strong');
    const status = document.createElement('span');
    const summary = document.createElement('p');
    const detail = document.createElement('small');
    code.textContent = String(entry?.code || 'CHECK').slice(0, 64);
    status.textContent = String(entry?.status || 'UNKNOWN').slice(0, 16);
    status.className = `is-${String(entry?.status || 'unknown').toLowerCase()}`;
    summary.textContent = String(entry?.suspected_cause || '').slice(0, 180);
    detail.textContent = `${String(entry?.related_config_key || 'fixed runtime')} · ${String(entry?.safe_manual_verification || '')}`.slice(0, 280);
    head.append(code, status);
    card.append(head, summary, detail);
    return card;
  }));
}

function renderNavigationStatus() {
  if (!navigationEngine) {
    navigationApiAvailable = false;
    ui.navigationSafetyBanner.className = 'navigation-safety-banner is-error';
    ui.navigationSafetyTitle.textContent = 'NAVIGATION MODULE ERROR';
    ui.navigationSafetyMessage.textContent = 'navigation.js를 불러오지 못했습니다. 페이지를 새로고침하세요.';
    return;
  }
  const snapshot = navigationSnapshot || {};
  const pipelineState = String(snapshot.pipeline?.state || 'idle').toLowerCase();
  const pipelineActive = navigationEngine.pipelineActive(snapshot);
  const pipelineRunning = pipelineState === 'running';
  const startup = navigationStartupPresentation(snapshot);
  const startupPending = startup?.pending === true;
  const goalState = String(snapshot.goal?.state || 'idle').toLowerCase();
  const goalActive = navigationEngine.goalActive(snapshot);
  const localizationState = String(snapshot.localization?.state || 'unknown').toLowerCase();
  const robotOnline = snapshot.robot_online === true;
  updateNavigationModelPanel();
  const available = navigationApiAvailable === true && snapshot.available === true;
  const manualConflict = navigationManualControlConflict();
  const safety = snapshot.safety || {};
  const blockers = Array.isArray(safety.blockers) ? safety.blockers : [];
  const firstBlocker = blockers[0];
  const activeMapMismatch = pipelineRunning && !navigationActiveMapMatchesSelection();
  renderNavigationHealth(snapshot);

  ui.navigationSafetyBanner.className = 'navigation-safety-banner';
  ui.navigationControlLink.hidden = !manualConflict;
  if (!navigationApiAvailable) {
    ui.navigationSafetyBanner.classList.add('is-offline');
    ui.navigationSafetyTitle.textContent = 'NAVIGATION API OFFLINE';
    ui.navigationSafetyMessage.textContent = '상태 API에 연결할 수 없습니다. 기존 STOP/CANCEL은 마지막 상태 기준으로 계속 시도할 수 있습니다.';
  } else if (!available) {
    ui.navigationSafetyBanner.classList.add('is-error');
    ui.navigationSafetyTitle.textContent = 'NAVIGATION UNAVAILABLE';
    ui.navigationSafetyMessage.textContent = snapshot.error || navigationBlockerMessage(firstBlocker || 'navigation_unavailable');
  } else if (activeMapMismatch) {
    ui.navigationSafetyBanner.classList.add('is-error');
    ui.navigationSafetyTitle.textContent = 'ACTIVE MAP REVISION MISMATCH';
    ui.navigationSafetyMessage.textContent = '현재 Nav2가 사용 중인 지도 revision과 Saved Maps catalog가 다릅니다. 새 pose·goal은 차단되었습니다.';
  } else if (manualConflict) {
    ui.navigationSafetyBanner.classList.add('is-warning');
    ui.navigationSafetyTitle.textContent = 'MANUAL CONTROL ACTIVE';
    ui.navigationSafetyMessage.textContent = '수동 제어와 Nav2는 동시에 명령할 수 없습니다. Controls에서 DISARM한 뒤 진행하세요.';
  } else if (!robotOnline) {
    ui.navigationSafetyBanner.classList.add('is-offline');
    ui.navigationSafetyTitle.textContent = 'ROBOT OFFLINE';
    ui.navigationSafetyMessage.textContent = '새 시작·초기 위치·목표 명령은 잠겼습니다. STOP과 CANCEL은 작업 정리를 위해 유지됩니다.';
  } else if (startup?.phase === 'failed') {
    ui.navigationSafetyBanner.classList.add('is-error');
    ui.navigationSafetyTitle.textContent = startup.label;
    ui.navigationSafetyMessage.textContent = startup.message;
  } else if (startupPending || ['starting_localization', 'waiting_localization', 'starting_navigation', 'warming_navigation', 'activating', 'stopping'].includes(startup?.phase)) {
    ui.navigationSafetyBanner.classList.add('is-warning');
    ui.navigationSafetyTitle.textContent = startup.label;
    ui.navigationSafetyMessage.textContent = startup.message;
  } else if (pipelineState === 'failed') {
    ui.navigationSafetyBanner.classList.add('is-error');
    ui.navigationSafetyTitle.textContent = 'NAVIGATION FAILED';
    ui.navigationSafetyMessage.textContent = snapshot.pipeline?.error || 'Nav2 pipeline 로그를 확인하세요.';
  } else if (firstBlocker) {
    ui.navigationSafetyBanner.classList.add('is-warning');
    ui.navigationSafetyTitle.textContent = 'ACTION REQUIRED';
    ui.navigationSafetyMessage.textContent = navigationBlockerMessage(firstBlocker);
  } else {
    ui.navigationSafetyTitle.textContent = pipelineRunning ? 'NAV2 RUNNING · SAFETY READY' : 'READY TO START';
    ui.navigationSafetyMessage.textContent = pipelineRunning
      ? '정적 지도와 위치추정 상태를 확인한 뒤 목표를 전송하세요.'
      : '정적 지도와 tuned parameter revision을 확인한 뒤 Nav2를 시작하세요.';
  }

  navigationStatusCard(
    ui.navigationPipelineState,
    ui.navigationPipelineNote,
    startup?.tone || (pipelineState === 'failed' ? 'error' : pipelineRunning ? 'ok' : 'waiting'),
    startup?.label || pipelineState.toUpperCase(),
    startup?.message || snapshot.pipeline?.error || (snapshot.pipeline?.job_id ? `job ${String(snapshot.pipeline.job_id).slice(0, 8)}` : 'pipeline idle'),
  );
  navigationStatusCard(
    ui.navigationRobotState,
    ui.navigationRobotNote,
    robotOnline ? 'ok' : 'error',
    robotOnline ? 'ONLINE' : 'OFFLINE',
    robotOnline ? '로봇 상태 수신 중' : '새 주행 명령 잠김',
  );
  navigationStatusCard(
    ui.navigationLocalizationState,
    ui.navigationLocalizationNote,
    localizationState === 'localized' ? 'ok' : ['lost', 'error'].includes(localizationState) ? 'error' : 'waiting',
    localizationState.toUpperCase(),
    startupPending ? startup.message : localizationState === 'localized' ? 'map frame pose ready' : localizationState === 'lost' ? '초기 위치 재설정 필요' :
      pipelineActive ? '초기 위치 필요' : 'START NAV2 후 초기 위치 필요',
  );
  navigationStatusCard(
    ui.navigationGoalState,
    ui.navigationGoalNote,
    goalState === 'succeeded' ? 'ok' : goalState === 'failed' ? 'error' : 'waiting',
    goalState.toUpperCase(),
    snapshot.goal?.error || (snapshot.goal?.goal_id ? `goal ${String(snapshot.goal.goal_id).slice(0, 8)}` : '목표 없음'),
  );

  const visibleJobId = snapshot.pipeline?.job_id || snapshot.localization_pipeline?.job_id;
  ui.navigationJobId.textContent = visibleJobId ? `JOB ${String(visibleJobId).slice(0, 8)}` : 'JOB —';
  ui.navigationReadiness.querySelectorAll('[data-navigation-ready]').forEach((element) => {
    const key = element.dataset.navigationReady;
    const value = snapshot.readiness?.[key];
    const needsInitialPose = pipelineRunning && key === 'localization' && value === false;
    const blocked = pipelineRunning && value === false && !needsInitialPose;
    element.classList.toggle('is-ok', value === true);
    element.classList.toggle('is-error', navigationApiAvailable === true && blocked);
    element.querySelector('strong').textContent = value === true ? 'READY' : needsInitialPose ? 'NEED POSE' : blocked ? 'BLOCKED' : 'WAIT';
  });
  const bindings = snapshot.bindings || {};
  ui.navigationScanBinding.textContent = bindings.scan || '/scan · XT16 360°';
  ui.navigationOdomBinding.textContent = bindings.odometry || '/utlidar/robot_odom';

  const distance = Number(snapshot.goal?.distance_remaining);
  const elapsed = Number(snapshot.goal?.navigation_time);
  const recoveries = Number(snapshot.goal?.recoveries);
  ui.navigationGoalDistance.textContent = Number.isFinite(distance) ? distance.toFixed(2) : '—';
  ui.navigationGoalElapsed.textContent = Number.isFinite(elapsed) ? `${elapsed.toFixed(1)} s` : '—';
  ui.navigationGoalRecoveries.textContent = Number.isFinite(recoveries) ? String(Math.max(0, Math.floor(recoveries))) : '0';
  const initialDistance = Number(snapshot.goal?.initial_distance);
  if (goalActive && Number.isFinite(distance) && Number.isFinite(initialDistance) && initialDistance > 0) {
    ui.navigationGoalProgress.value = Math.max(0, Math.min(1, 1 - distance / initialDistance));
  } else if (goalActive) {
    ui.navigationGoalProgress.removeAttribute('value');
  } else {
    ui.navigationGoalProgress.value = goalState === 'succeeded' ? 1 : 0;
  }
  ui.navigationGoalMessage.textContent = snapshot.goal?.error || snapshot.goal?.message || (
    goalState === 'active' ? 'Nav2가 목표 경로를 추종하고 있습니다.' :
      goalState === 'succeeded' ? '목표에 도착했습니다.' :
        'Nav2를 시작하고 초기 위치를 지정한 뒤 목표를 보낼 수 있습니다.'
  );

  const mapReady = Boolean(
    navigationSelectedMapMeta &&
    navigationMapSnapshot &&
    navigationSelectedMapMeta.revision === navigationMapSnapshot.revision
  );
  const parameterReady = Boolean(navigationParameterSnapshot?.revision);
  const canStart = available && robotOnline && mapReady && parameterReady &&
    safety.can_start === true && !pipelineActive && !manualConflict;
  const canStop = safety.can_stop === true || pipelineActive;
  ui.navigationStartButton.disabled = navigationOperationBusy || manualConflict || !canStart;
  ui.navigationStartButton.textContent = startupPending ? 'STARTING…' : 'START NAV2';
  ui.navigationStopButton.textContent = startupPending ? 'STOP STARTUP' : 'STOP';
  ui.navigationStopButton.disabled = (navigationOperationBusy && navigationOperationKind !== 'start') || !canStop;
  ui.navigationCancelGoal.disabled = navigationOperationBusy || !goalActive;
  ui.navigationClearCostmaps.disabled = navigationOperationBusy || !pipelineRunning;
  ui.navigationMapSelect.disabled = navigationOperationBusy || pipelineActive;
  if (!mapAnnotationFeature?.hasActiveTool()) {
    ui.navigationMapHint.textContent = activeMapMismatch
      ? '활성 지도 revision이 변경되었습니다. STOP 후 정적 지도를 다시 선택하세요.'
      : !mapReady
      ? 'Saved Maps의 2D 지도를 불러와야 위치를 지정할 수 있습니다.'
      : startupPending ? startup.message
      : !pipelineRunning ? 'START NAV2가 위치추정 센서와 Nav2를 순서대로 준비합니다.'
        : localizationState !== 'localized' ? 'INITIAL POSE를 선택하고 현재 로봇 위치에서 진행 방향으로 드래그하세요.'
          : 'GOAL POSE를 선택하고 목표 위치에서 도착 방향으로 드래그하세요.';
  }
  if (navigationMapError || activeMapMismatch) setStatePill(ui.navigationMapState, 'error', 'MAP ERROR');
  else if (mapReady) setStatePill(ui.navigationMapState, 'ok', 'STATIC MAP');
  else setStatePill(ui.navigationMapState, 'waiting', 'NO MAP');
  renderNavigationPoseSelection();
  mapAnnotationFeature?.render();
  syncNavigationParameterControls();
  scheduleNavigationMapDraw();
  navigationLogFeature?.render();
}

function applyNavigationSnapshot(payload) {
  const snapshot = extractNavigationSnapshot(payload);
  if (!snapshot) throw new Error('서버가 유효한 navigation snapshot을 반환하지 않았습니다.');
  navigationSnapshot = snapshot;
  navigationApiAvailable = true;
  renderNavigationStatus();
  renderControlStatus();
  const serverMapId = String(snapshot.map?.id || '');
  const serverMapRevision = String(snapshot.map?.revision || '');
  if (serverMapId && (
    navigationSelectedMapMeta?.id !== serverMapId ||
    String(navigationSelectedMapMeta?.revision || '') !== serverMapRevision
  )) syncNavigationMapOptions();
  return snapshot;
}

async function refreshNavigation() {
  if (navigationStatusBusy || navigationOperationBusy) return;
  navigationStatusBusy = true;
  const generation = navigationStatusRequestGeneration;
  try {
    const payload = await api('/api/v1/navigation');
    if (generation !== navigationStatusRequestGeneration) return;
    applyNavigationSnapshot(payload);
  } catch (_) {
    if (generation !== navigationStatusRequestGeneration) return;
    navigationApiAvailable = false;
    renderNavigationStatus();
    renderControlStatus();
  } finally {
    navigationStatusBusy = false;
  }
}

async function runNavigationMutation(path, body, successMessage) {
  if (navigationOperationBusy) return null;
  navigationOperationBusy = true;
  navigationOperationKind = path.endsWith('/start') ? 'start' : path.endsWith('/stop') ? 'stop' : 'command';
  navigationStatusRequestGeneration += 1;
  renderNavigationStatus();
  let response = null;
  try {
    response = await api(path, { method: 'POST', body: JSON.stringify(body) });
    try { applyNavigationSnapshot(response); } catch (_) {}
    if (successMessage) showToast(successMessage);
    return response;
  } catch (error) {
    showToast(`Navigation 명령 실패: ${error.message}`, true);
    return null;
  } finally {
    navigationOperationBusy = false;
    navigationOperationKind = '';
    renderNavigationStatus();
    void refreshNavigation();
  }
}

async function startNavigation() {
  if (mapAnnotationFeature?.hasDirty() || mapAnnotationFeature?.hasActiveTool()) {
    showToast('지도 주석을 저장하거나 DISCARD한 뒤 Nav2를 시작하세요.', true);
    return;
  }
  if (navigationManualControlConflict()) {
    showToast('Controls에서 수동 제어를 DISARM한 뒤 Nav2를 시작하세요.', true);
    return;
  }
  if (!navigationSelectedMapMeta || !navigationMapSnapshot || !navigationParameterSnapshot) {
    showToast('정적 지도와 파라미터 revision이 모두 필요합니다.', true);
    return;
  }
  await runNavigationMutation('/api/v1/navigation/start', {
    map_id: navigationSelectedMapMeta.id,
    map_revision: navigationSelectedMapMeta.revision,
    parameters_revision: navigationParameterSnapshot.revision,
  }, 'Navigation 시작 작업을 접수했습니다. 이 화면에서 센서·Nav2 준비 상태를 확인할 수 있습니다.');
}

async function stopNavigation() {
  const canStop = navigationSnapshot?.safety?.can_stop === true ||
    navigationEngine?.pipelineActive(navigationSnapshot);
  if (!canStop) return;
  discardNavigationPose();
  await runNavigationMutation('/api/v1/navigation/stop', {}, 'Nav2 중지를 요청했습니다.');
}

async function sendNavigationPose() {
  const staged = navigationStagedPose;
  if (!staged || !navigationSelectedMapMeta || !navigationPoseToolAllowed(staged.mode)) return;
  if (navigationManualControlConflict()) {
    showToast('수동 제어가 활성화되어 위치·목표 명령을 보낼 수 없습니다.', true);
    return;
  }
  if (staged.mode === 'goal' && !window.confirm('주변이 비어 있고 물리 리모컨을 즉시 사용할 수 있나요? 확인을 누르면 로봇이 자율 이동을 시작할 수 있습니다.')) {
    return;
  }
  const endpoint = staged.mode === 'goal' ? '/api/v1/navigation/goal' : '/api/v1/navigation/initial-pose';
  const body = {
    map_id: navigationSelectedMapMeta.id,
    map_revision: navigationSelectedMapMeta.revision,
    pose: { x: staged.x, y: staged.y, yaw: staged.yaw },
  };
  if (staged.mode === 'goal') body.confirmed = true;
  const response = await runNavigationMutation(endpoint, {
    ...body,
  }, staged.mode === 'goal' ? 'Nav2 목표를 전송했습니다.' : '초기 위치를 전송했습니다.');
  if (response) {
    navigationMapTool = '';
    discardNavigationPose();
  }
}

async function cancelNavigationGoal() {
  const goalId = String(navigationSnapshot?.goal?.goal_id || '');
  if (!goalId || !navigationEngine?.goalActive(navigationSnapshot)) return;
  await runNavigationMutation('/api/v1/navigation/cancel', { goal_id: goalId }, '활성 목표 취소를 요청했습니다.');
}

async function clearNavigationCostmaps() {
  if (String(navigationSnapshot?.pipeline?.state || '').toLowerCase() !== 'running') return;
  await runNavigationMutation('/api/v1/navigation/clear-costmaps', { scope: 'both' }, '전역·로컬 costmap 초기화를 요청했습니다.');
}

function navigationParameterPresets() {
  if (!navigationEngine) return [];
  const presets = [...(navigationParameterSnapshot?.presets || [])];
  if (!presets.some((preset) => preset.id === 'pdf11_go2_indoor')) {
    presets.unshift({
      id: 'pdf11_go2_indoor',
      label: 'PDF 11 · Go2 indoor tuned',
      description: '수업 자료의 Go2 실내 주행 기준값',
      values: navigationEngine.TUNED_VALUES,
    });
  }
  return presets;
}

function renderNavigationParameterGroups(values = navigationParameterDraft || navigationEngine?.TUNED_VALUES, disabled = false) {
  if (!navigationEngine || !values) {
    ui.navigationParameterGroups.innerHTML = '<div class="sensor-placeholder">Navigation parameter module unavailable</div>';
    return;
  }
  ui.navigationParameterGroups.innerHTML = navigationEngine.GROUPS.map((group) => {
    const fields = navigationEngine.FIELDS.filter((field) => field.group === group.id);
    return `<section class="navigation-parameter-group" data-navigation-parameter-group="${escapeHtml(group.id)}">
      <header><strong>${escapeHtml(group.label)}</strong><small>${escapeHtml(group.description)}</small></header>
      <div class="navigation-parameter-fields">${fields.map((field) => {
        const value = values[field.key];
        const locked = field.locked === true;
        const control = field.type === 'boolean'
          ? `<select data-navigation-parameter="${escapeHtml(field.key)}" ${disabled || locked ? 'disabled' : ''}><option value="true" ${value === true ? 'selected' : ''}>TRUE</option><option value="false" ${value === false ? 'selected' : ''}>FALSE</option></select>`
          : `<input data-navigation-parameter="${escapeHtml(field.key)}" type="number" min="${field.minimum}" max="${field.maximum}" step="${field.step}" value="${escapeHtml(value)}" ${disabled || locked ? 'disabled' : ''}>`;
        return `<label class="navigation-parameter-field${locked ? ' is-locked' : ''}" data-navigation-parameter-row="${escapeHtml(field.key)}"><span><b>${escapeHtml(field.label)}${field.unit ? ` · ${escapeHtml(field.unit)}` : ''}${locked ? ' · LOCKED' : ''}</b><small>${escapeHtml(field.help)}</small></span>${control}</label>`;
      }).join('')}</div>
    </section>`;
  }).join('');
}

function renderNavigationPresetOptions() {
  const presets = navigationParameterPresets();
  ui.navigationPreset.innerHTML = presets.length
    ? presets.map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`).join('')
    : '<option value="">사용 가능한 preset 없음</option>';
  const preferred = navigationParameterSnapshot?.active_preset || 'pdf11_go2_indoor';
  ui.navigationPreset.value = presets.some((preset) => preset.id === preferred) ? preferred : presets[0]?.id || '';
}

function navigationParameterValidation() {
  if (!navigationEngine || !navigationParameterSnapshot || !navigationParameterDraft) {
    throw new Error('서버 parameter snapshot이 없습니다.');
  }
  return navigationEngine.parameterValues(navigationParameterDraft, { requireAll: true });
}

function navigationParametersDirty() {
  if (!navigationEngine || !navigationParameterSnapshot || !navigationParameterDraft) return false;
  try {
    return Object.keys(navigationEngine.changedParameterValues(
      navigationParameterSnapshot.values,
      navigationParameterDraft,
    )).length > 0;
  } catch (_) {
    return true;
  }
}

function syncNavigationParameterControls() {
  const pipelineActive = navigationEngine?.pipelineActive(navigationSnapshot) || false;
  const ready = Boolean(navigationEngine && navigationParameterSnapshot && navigationParameterDraft);
  let validationError = '';
  let changes = {};
  if (ready) {
    try {
      navigationParameterValidation();
      changes = navigationEngine.changedParameterValues(navigationParameterSnapshot.values, navigationParameterDraft);
    } catch (error) {
      validationError = error.message;
    }
  }
  const dirty = ready && (validationError || Object.keys(changes).length > 0);
  ui.navigationParameterGroups.querySelectorAll('[data-navigation-parameter]').forEach((input) => {
    const field = navigationEngine.FIELD_BY_KEY[input.dataset.navigationParameter];
    input.disabled = navigationParameterBusy || !ready || field?.locked === true;
  });
  ui.navigationParameterGroups.querySelectorAll('[data-navigation-parameter-row]').forEach((row) => {
    row.classList.toggle('is-changed', Object.hasOwn(changes, row.dataset.navigationParameterRow));
  });
  ui.navigationPreset.disabled = navigationParameterBusy || !ready;
  ui.navigationPresetLoad.disabled = navigationParameterBusy || !ready || !ui.navigationPreset.value;
  ui.navigationParameterReset.disabled = navigationParameterBusy || !dirty;
  ui.navigationParameterApply.disabled = navigationParameterBusy || pipelineActive || !dirty || Boolean(validationError);
  ui.navigationParameterDirty.textContent = validationError
    ? 'INVALID VALUES'
    : dirty ? `${Object.keys(changes).length} CHANGED` : 'NO CHANGES';
  ui.navigationParameterDirty.classList.toggle('is-dirty', Boolean(dirty));
  if (!ready) {
    setStatePill(ui.navigationParameterState, 'error', 'UNAVAILABLE');
    ui.navigationParameterMessage.textContent = '서버가 27개 tuned parameter와 revision을 모두 제공해야 편집·적용할 수 있습니다.';
    ui.navigationParameterMessage.classList.add('is-error');
  } else if (validationError) {
    setStatePill(ui.navigationParameterState, 'error', 'INVALID');
    ui.navigationParameterMessage.textContent = `파라미터 검증 실패: ${validationError}`;
    ui.navigationParameterMessage.classList.add('is-error');
  } else if (pipelineActive && dirty) {
    setStatePill(ui.navigationParameterState, 'waiting', 'RESTART REQUIRED');
    ui.navigationParameterMessage.textContent = '변경값은 유지됩니다. STOP으로 Nav2를 중지한 뒤 APPLY하세요.';
    ui.navigationParameterMessage.classList.remove('is-error');
  } else if (dirty) {
    setStatePill(ui.navigationParameterState, 'waiting', 'MODIFIED');
    ui.navigationParameterMessage.textContent = '아직 서버에 적용되지 않은 값입니다. APPLY 후 Nav2를 시작하세요.';
    ui.navigationParameterMessage.classList.remove('is-error');
  } else {
    setStatePill(ui.navigationParameterState, 'ok', 'APPLIED');
    ui.navigationParameterMessage.textContent = navigationParameterSnapshot.requires_restart
      ? '현재 revision이 적용되어 있습니다. 이후 변경은 Nav2 중지 상태에서 저장되고 다음 시작에 사용됩니다.'
      : '현재 revision이 적용되어 있습니다.';
    ui.navigationParameterMessage.classList.remove('is-error');
  }
}

function updateNavigationParameterDraft(event) {
  const input = event.target.closest('[data-navigation-parameter]');
  if (!input || !navigationParameterDraft || !navigationEngine) return;
  const key = input.dataset.navigationParameter;
  try {
    const value = navigationEngine.coerceParameterValue(key, input.value);
    navigationParameterDraft = { ...navigationParameterDraft, [key]: value };
  } catch (_) {
    navigationParameterDraft = { ...navigationParameterDraft, [key]: input.value };
  }
  syncNavigationParameterControls();
}

async function refreshNavigationParameters(force = false) {
  if (!navigationEngine || navigationParameterBusy || (navigationParameterSnapshot && !force)) {
    syncNavigationParameterControls();
    return;
  }
  navigationParameterBusy = true;
  setStatePill(ui.navigationParameterState, 'waiting', 'LOADING');
  syncNavigationParameterControls();
  try {
    const payload = await api('/api/v1/navigation/parameters');
    const raw = payload?.parameters && typeof payload.parameters === 'object' ? payload.parameters : payload;
    navigationParameterSnapshot = navigationEngine.normalizeParameterSnapshot(raw);
    navigationParameterDraft = { ...navigationParameterSnapshot.values };
    renderNavigationPresetOptions();
    renderNavigationParameterGroups(navigationParameterDraft);
  } catch (error) {
    navigationParameterSnapshot = null;
    navigationParameterDraft = null;
    renderNavigationPresetOptions();
    renderNavigationParameterGroups(navigationEngine.TUNED_VALUES, true);
    ui.navigationParameterMessage.textContent = `파라미터 API 확인 실패: ${error.message}`;
    ui.navigationParameterMessage.classList.add('is-error');
  } finally {
    navigationParameterBusy = false;
    syncNavigationParameterControls();
    renderNavigationStatus();
  }
}

function loadNavigationPreset() {
  if (!navigationParameterSnapshot || navigationParameterBusy) return;
  const preset = navigationParameterPresets().find((item) => item.id === ui.navigationPreset.value);
  if (!preset) return;
  try {
    navigationParameterDraft = navigationEngine.parameterValues(preset.values, { requireAll: true });
    renderNavigationParameterGroups(navigationParameterDraft);
    syncNavigationParameterControls();
    showToast(`${preset.label} 값을 draft에 불러왔습니다. APPLY 전에는 서버 값이 바뀌지 않습니다.`);
  } catch (error) {
    showToast(`Preset 로드 실패: ${error.message}`, true);
  }
}

function resetNavigationParameterDraft() {
  if (!navigationParameterSnapshot || navigationParameterBusy) return;
  navigationParameterDraft = { ...navigationParameterSnapshot.values };
  renderNavigationParameterGroups(navigationParameterDraft);
  syncNavigationParameterControls();
}

async function applyNavigationParameters() {
  if (!navigationParameterSnapshot || navigationParameterBusy) return;
  if (navigationEngine.pipelineActive(navigationSnapshot)) {
    showToast('Nav2를 STOP한 뒤 파라미터를 적용하세요.', true);
    return;
  }
  let patch;
  try {
    patch = navigationEngine.parameterPatch(
      navigationParameterSnapshot.revision,
      navigationParameterSnapshot.values,
      navigationParameterDraft,
    );
  } catch (error) {
    showToast(`파라미터 검증 실패: ${error.message}`, true);
    return;
  }
  if (!Object.keys(patch.values).length) {
    showToast('적용할 변경 사항이 없습니다.');
    return;
  }
  navigationParameterBusy = true;
  let reloadAfterConflict = false;
  syncNavigationParameterControls();
  try {
    const response = await api('/api/v1/navigation/parameters', {
      method: 'PATCH',
      body: JSON.stringify({
        base_revision: patch.base_revision,
        values: patch.values,
      }),
    });
    const raw = response?.parameters && typeof response.parameters === 'object' ? response.parameters : response;
    navigationParameterSnapshot = navigationEngine.normalizeParameterSnapshot(raw);
    navigationParameterDraft = { ...navigationParameterSnapshot.values };
    renderNavigationPresetOptions();
    renderNavigationParameterGroups(navigationParameterDraft);
    showToast('Navigation 파라미터를 적용했습니다. 다음 Nav2 시작에 사용됩니다.');
  } catch (error) {
    showToast(`파라미터 적용 실패: ${error.message}`, true);
    reloadAfterConflict = error.status === 409 || String(error.message).includes('409');
  } finally {
    navigationParameterBusy = false;
    syncNavigationParameterControls();
    renderNavigationStatus();
  }
  if (reloadAfterConflict) {
    await refreshNavigationParameters(true);
    showToast('파라미터 revision이 변경되어 최신 값을 다시 불러왔습니다. 변경 사항을 다시 확인하세요.', true);
  }
}

function redrawActiveMap() {
  const desired = desiredMapView();
  setMapLayerVisibility(desired);
  if (desired === 'occupancy' && lastMapSnapshot) drawOccupancyMap(lastMapSnapshot, false);
  else if (desired === 'projection') drawLivePointProjection(lastCloudSnapshot);
  else if (desired === 'cloud') drawPointcloud(lastCloudSnapshot);
}

function redrawSavedMap() {
  setSavedMapLayerVisibility(savedMapViewPreference);
  if (savedMapViewPreference === 'occupancy') {
    if (savedOccupancySnapshot) drawOccupancyMap(savedOccupancySnapshot, true);
    else setStatePill(ui.savedMappingState, 'waiting', 'LOADING 2D MAP');
  } else {
    drawSavedPointcloud();
  }
  updateSavedMapOverview();
}

function desiredMapView() {
  // A latched ROS OccupancyGrid is valid independently of the ICMP link KPI.
  // Requiring ping here made a perfectly usable map disappear during brief
  // network-health probe failures.
  const liveGridReady = Boolean(latestState?.sources?.occupancy_grid && lastMapSnapshot?.data_b64);
  const liveCloudReady = Boolean(liveSceneCloud());
  if (mapViewPreference === 'occupancy') {
    return liveGridReady ? 'occupancy' : 'projection';
  }
  if (mapViewPreference === 'projection') return 'projection';
  if (mapViewPreference === 'cloud') return 'cloud';
  return liveGridReady ? 'occupancy' : liveCloudReady ? 'projection' : 'cloud';
}

function chooseMapView(mode) {
  mapViewPreference = ['cloud', 'projection', 'occupancy', 'auto'].includes(mode) ? mode : 'cloud';
  ui.mapViewMode.value = mapViewPreference;
  redrawActiveMap();
  syncPointcloudTransport();
  if (latestState) updateOverview(latestState);
  if (mapViewPreference === 'occupancy' && desiredMapView() === 'projection') {
    showToast('ROS OccupancyGrid가 없어 동일한 라이브 점군의 2D 투영으로 표시합니다.');
  }
}

function chooseSavedMapView(mode) {
  const kind = mode === 'occupancy' ? 'occupancy2d' : 'pointcloud3d';
  const candidate = savedMapCatalog.find((entry) => entry.kind === kind);
  if (candidate) {
    selectSavedMap(candidate.id);
    return;
  }
  if (mode === 'cloud' && offlineCloudSnapshot) {
    selectSavedMap('__fallback_cloud');
    return;
  }
  savedMapViewPreference = mode === 'occupancy' && savedOccupancySnapshot ? 'occupancy' : 'cloud';
  ui.savedMapViewMode.value = savedMapViewPreference;
  redrawSavedMap();
}

function drawMapOverlay(ctx, viewport) {
  if (!mapOverlayVisible || !currentPose) return;
  const framesMatch = !viewport.frameId || !currentPose.frameId || viewport.frameId === currentPose.frameId;
  const poseProjection = viewport.projectWorld(currentPose);
  const anchor = framesMatch && poseProjection.inside
    ? poseProjection
    : {
        x: viewport.width / 2,
        y: viewport.height / 2,
        heading: poseProjection.heading,
        inside: false,
        frameMismatch: !framesMatch,
      };
  const fallbackProject = (pose) => ({
    x: anchor.x + (pose.x - currentPose.x) * viewport.fallbackScale,
    y: anchor.y - (pose.y - currentPose.y) * viewport.fallbackScale,
  });
  const projectedTrail = poseTrail.map((pose) => {
    const projected = viewport.projectWorld(pose);
    return framesMatch && projected.inside && poseProjection.inside ? projected : fallbackProject(pose);
  }).filter((point) => point.x > -20 && point.x < viewport.width + 20 && point.y > -20 && point.y < viewport.height + 20);
  const unit = viewport.ratio;

  ctx.save();
  ctx.lineCap = 'round';
  if (projectedTrail.length > 1) {
    ctx.beginPath();
    projectedTrail.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.strokeStyle = 'rgba(162, 139, 255, .76)';
    ctx.lineWidth = 1.5 * unit;
    ctx.setLineDash([4 * unit, 5 * unit]);
    ctx.stroke();
    ctx.setLineDash([]);
    projectedTrail.forEach((point, index) => {
      const alpha = .18 + (.52 * (index + 1) / projectedTrail.length);
      ctx.fillStyle = `rgba(162, 139, 255, ${alpha})`;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 1.8 * unit, 0, Math.PI * 2);
      ctx.fill();
    });
  }
  drawQuadruped(ctx, anchor.x, anchor.y, anchor.heading, unit);
  drawPoseLabel(ctx, anchor, viewport, unit);
  ctx.restore();
}

function drawQuadruped(ctx, x, y, heading, unit) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(heading);
  ctx.shadowColor = 'rgba(125, 240, 182, .76)';
  ctx.shadowBlur = 13 * unit;
  ctx.strokeStyle = '#c9ffe6';
  ctx.fillStyle = 'rgba(31, 102, 78, .94)';
  ctx.lineWidth = 1.35 * unit;
  const legLength = 12 * unit;
  const legOffsets = [[5, 8], [5, -8], [-7, 8], [-7, -8]];
  ctx.beginPath();
  legOffsets.forEach(([legX, legY]) => {
    ctx.moveTo(legX * unit, legY * unit);
    ctx.lineTo((legX + (legX > 0 ? 4 : -3)) * unit, (legY + (legY > 0 ? 1 : -1)) * unit);
  });
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(13 * unit, 0);
  ctx.lineTo(5 * unit, 7 * unit);
  ctx.lineTo(-10 * unit, 6 * unit);
  ctx.lineTo(-13 * unit, 0);
  ctx.lineTo(-10 * unit, -6 * unit);
  ctx.lineTo(5 * unit, -7 * unit);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = '#ecfff5';
  ctx.beginPath();
  ctx.moveTo(17 * unit, 0);
  ctx.lineTo(8 * unit, -3 * unit);
  ctx.lineTo(8 * unit, 3 * unit);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawPoseLabel(ctx, anchor, viewport, unit) {
  const xText = `X ${currentPose.x.toFixed(2)} m`;
  const yText = `Y ${currentPose.y.toFixed(2)} m`;
  const yawDegrees = ((currentPose.yaw * 180 / Math.PI) + 360) % 360;
  const headingText = `${viewport.mode} · ${yawDegrees.toFixed(0)}°`;
  const fontSize = 9 * unit;
  ctx.font = `600 ${fontSize}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  const labelWidth = Math.max(ctx.measureText(xText).width, ctx.measureText(yText).width, ctx.measureText(headingText).width) + 14 * unit;
  const labelHeight = 39 * unit;
  const labelX = Math.min(viewport.width - labelWidth - 8 * unit, Math.max(8 * unit, anchor.x + 18 * unit));
  const labelY = Math.max(8 * unit, anchor.y - labelHeight - 10 * unit);
  ctx.fillStyle = 'rgba(5, 16, 13, .86)';
  ctx.strokeStyle = 'rgba(125, 240, 182, .38)';
  ctx.lineWidth = unit;
  ctx.beginPath();
  ctx.roundRect(labelX, labelY, labelWidth, labelHeight, 5 * unit);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = '#d9fff0';
  ctx.fillText(xText, labelX + 7 * unit, labelY + 12 * unit);
  ctx.fillText(yText, labelX + 7 * unit, labelY + 23 * unit);
  ctx.fillStyle = '#8fa9a1';
  ctx.font = `500 ${7 * unit}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  ctx.fillText(headingText, labelX + 7 * unit, labelY + 33 * unit);
  if (!anchor.inside) {
    ctx.fillStyle = 'rgba(255, 198, 109, .9)';
    ctx.font = `600 ${7 * unit}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    ctx.fillText(anchor.frameMismatch ? 'FRAME RELATIVE' : 'RELATIVE VIEW', labelX + labelWidth - 72 * unit, labelY + 33 * unit);
  }
}

const CAMERA_PREFERENCE_KEY = 'robot-scope.camera-view.v1';
const CAMERA_FRAME_FRESH_MS = 3000;
const CAMERA_RECORD_MAX_MS = 10 * 60 * 1000;
const CAMERA_RECORD_MAX_BYTES = 256 * 1024 * 1024;

function normalizeCameraCatalog(payload) {
  const sources = Array.isArray(payload?.sources) ? payload.sources : [];
  const normalized = [];
  const seen = new Set();
  for (const entry of sources) {
    if (!entry || typeof entry !== 'object') continue;
    const id = String(entry.id || entry.source_id || '').trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const state = String(entry.state || (entry.live ? 'live' : 'waiting')).trim().toLowerCase() || 'waiting';
    const fps = entry.fps == null ? Number.NaN : Number(entry.fps);
    const age = entry.age_s == null ? Number.NaN : Number(entry.age_s);
    normalized.push({
      ...entry,
      id,
      source_id: id,
      label: String(entry.label || id),
      topic: String(entry.topic || entry.stream_id || '—'),
      transport: String(entry.transport || '—'),
      state,
      fps: Number.isFinite(fps) ? fps : null,
      age_s: Number.isFinite(age) ? age : null,
      width: Number(entry.width) || 0,
      height: Number(entry.height) || 0,
      available: entry.available != null
        ? Boolean(entry.available)
        : Boolean(entry.live || ['ok', 'live', 'ready', 'streaming', 'waiting', 'stale'].includes(state)),
    });
  }
  const rawMaxActive = Number(payload?.max_active ?? payload?.max_viewers ?? 1);
  const maxActive = Math.max(1, Math.min(2, Number.isFinite(rawMaxActive) ? Math.floor(rawMaxActive) : 1));
  return { maxActive, sources: normalized };
}

function cameraSourceForId(sourceId) {
  return cameraCatalog.find((source) => source.id === sourceId) || null;
}

function preferredCameraSource(sources, requestedId = '') {
  if (requestedId && sources.some((source) => source.id === requestedId)) return requestedId;
  return (sources.find((source) => source.available) || sources[0])?.id || '';
}

function secondaryCameraSource(sources, primaryId) {
  return (sources.find((source) => source.id !== primaryId && source.available)
    || sources.find((source) => source.id !== primaryId))?.id || '';
}

function loadCameraPreferences(storage = window.localStorage) {
  try {
    const parsed = JSON.parse(storage.getItem(CAMERA_PREFERENCE_KEY) || '{}');
    return {
      viewMode: parsed.viewMode === 'dual' ? 'dual' : 'single',
      primarySourceId: typeof parsed.primarySourceId === 'string' ? parsed.primarySourceId : '',
    };
  } catch (_) {
    return { viewMode: 'single', primarySourceId: '' };
  }
}

function persistCameraPreferences(storage = window.localStorage) {
  try {
    storage.setItem(CAMERA_PREFERENCE_KEY, JSON.stringify({
      viewMode: cameraViewMode,
      primarySourceId: cameraPrimarySourceId,
    }));
  } catch (_) {
    // Safari private browsing and locked-down kiosk profiles can reject storage.
  }
}

function createCameraSlotRuntime(role, elements) {
  return {
    role,
    ...elements,
    sourceId: '',
    socket: null,
    socketGeneration: 0,
    reconnectTimer: 0,
    meta: null,
    statusMeta: null,
    lastFrameAt: 0,
    activeSourceKey: '',
    frames: 0,
    frameWindow: [],
    imageDecodeQueue: null,
    videoDecoder: null,
    hasKey: false,
  };
}

function getCameraSlots() {
  if (cameraSlotRuntimes) return cameraSlotRuntimes;
  cameraSlotRuntimes = {
    primary: createCameraSlotRuntime('primary', {
      root: ui.cameraPrimarySlot,
      canvas: ui.cameraCanvas,
      empty: ui.cameraEmpty,
      emptyText: ui.cameraEmptyText,
      label: ui.cameraPrimaryLabel,
      sourceIdLabel: ui.cameraPrimarySourceId,
      state: ui.cameraPrimaryState,
      fps: ui.cameraPrimaryFps,
      topic: ui.cameraPrimaryTopic,
      transport: ui.cameraPrimaryTransport,
      topicOverlay: ui.cameraTopicLabel,
      codecOverlay: ui.cameraCodecLabel,
    }),
    secondary: createCameraSlotRuntime('secondary', {
      root: ui.cameraSecondarySlot,
      canvas: ui.cameraSecondaryCanvas,
      empty: ui.cameraSecondaryEmpty,
      emptyText: ui.cameraSecondaryEmptyText,
      label: ui.cameraSecondaryLabel,
      sourceIdLabel: ui.cameraSecondarySourceId,
      state: ui.cameraSecondaryState,
      fps: ui.cameraSecondaryFps,
      topic: ui.cameraSecondaryTopic,
      transport: ui.cameraSecondaryTransport,
      topicOverlay: ui.cameraSecondaryTopicLabel,
      codecOverlay: ui.cameraSecondaryCodecLabel,
    }),
  };
  return cameraSlotRuntimes;
}

function primaryCameraSlot() {
  return getCameraSlots().primary;
}

function cameraSlotMetadata(slot) {
  const source = cameraSourceForId(slot.sourceId) || {};
  return { ...source, ...(slot.statusMeta || {}), ...(slot.meta || {}), id: slot.sourceId || source.id || '' };
}

function cameraSlotFrameAvailable(slot, now = Date.now()) {
  return Boolean(
    slot?.canvas?.width > 1
    && slot?.canvas?.height > 1
    && cameraFrameIsFresh(slot.lastFrameAt, cameraSlotMetadata(slot), now),
  );
}

function formatCameraFps(value) {
  const fps = Number(value);
  return Number.isFinite(fps) && fps >= 0 ? `${fps.toFixed(fps >= 10 ? 1 : 2)} FPS` : '— FPS';
}

function renderCameraSlotIdentity(slot, now = Date.now()) {
  const source = cameraSourceForId(slot.sourceId);
  const metadata = cameraSlotMetadata(slot);
  const fresh = cameraSlotFrameAvailable(slot, now);
  const state = String(
    fresh
      ? 'live'
      : (slot.lastFrameAt ? 'stale' : (metadata.state || (source?.available ? 'waiting' : 'unavailable'))),
  ).toLowerCase();
  const topic = String(metadata.topic || source?.topic || '—');
  const transport = String(metadata.transport || source?.transport || '—');
  const width = Number(metadata.width || source?.width || 0);
  const height = Number(metadata.height || source?.height || 0);
  const format = String(metadata.format || '').toUpperCase();
  const dimensions = width && height ? `${width}×${height}` : '';
  slot.label.textContent = source?.label || metadata.label || (slot.sourceId ? slot.sourceId : '카메라 없음');
  slot.sourceIdLabel.textContent = slot.sourceId || 'NO SOURCE';
  slot.sourceIdLabel.title = slot.sourceId || '';
  slot.state.textContent = state.toUpperCase();
  slot.state.dataset.state = state;
  slot.fps.textContent = formatCameraFps(metadata.fps ?? source?.fps);
  slot.topic.textContent = `TOPIC ${topic}`;
  slot.topic.title = topic;
  slot.transport.textContent = `TRANSPORT ${transport}`;
  slot.transport.title = transport;
  slot.topicOverlay.textContent = `${slot.sourceId || 'NO SOURCE'} · ${topic}`;
  slot.codecOverlay.textContent = [format, dimensions, transport].filter(Boolean).join(' · ') || '—';
  if (slot.role === 'primary') {
    setStatePill(ui.cameraState, state, state === 'live' ? 'LIVE' : state.toUpperCase());
  }
}

function renderCameraCatalogUi() {
  const selected = cameraPrimarySourceId;
  ui.cameraPrimarySource.innerHTML = '';
  if (!cameraCatalog.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = '카메라 없음';
    ui.cameraPrimarySource.appendChild(option);
  } else {
    for (const source of cameraCatalog) {
      const option = document.createElement('option');
      option.value = source.id;
      option.textContent = `${source.label} · ${source.id}`;
      option.disabled = !source.available;
      ui.cameraPrimarySource.appendChild(option);
    }
  }
  ui.cameraPrimarySource.value = selected;
  ui.cameraPrimarySource.disabled = cameraCatalog.length < 2;
  const dualAvailable = cameraMaxActive >= 2 && cameraCatalog.length >= 2;
  ui.cameraDualMode.disabled = !dualAvailable;
  if (!dualAvailable && cameraViewMode === 'dual') cameraViewMode = 'single';
  ui.cameraSingleMode.setAttribute('aria-pressed', String(cameraViewMode === 'single'));
  ui.cameraDualMode.setAttribute('aria-pressed', String(cameraViewMode === 'dual'));
  ui.cameraViewGrid.dataset.viewMode = cameraViewMode;
  ui.cameraViewGrid.closest('.camera-panel')?.classList.toggle('is-dual-view', cameraViewMode === 'dual');
  ui.cameraSecondarySlot.hidden = cameraViewMode !== 'dual';
  const visibleSlots = cameraViewMode === 'dual'
    ? [getCameraSlots().primary, getCameraSlots().secondary]
    : [getCameraSlots().primary];
  const requestedSources = visibleSlots.filter((slot) => slot.sourceId).length;
  const connectedSources = visibleSlots.filter(
    (slot) => slot.socket?.readyState === WebSocket.OPEN,
  ).length;
  ui.cameraCapacity.textContent = `${connectedSources} CONNECTED · ${requestedSources} REQUESTED`;
  renderCameraSlotIdentity(getCameraSlots().primary);
  renderCameraSlotIdentity(getCameraSlots().secondary);
}

function setCameraSlotSource(role, sourceId, reason = '') {
  const slot = getCameraSlots()[role];
  const nextSourceId = String(sourceId || '');
  if (slot.sourceId === nextSourceId) return false;
  disconnectCameraSlot(slot);
  slot.sourceId = nextSourceId;
  slot.statusMeta = cameraSourceForId(nextSourceId);
  if (role === 'primary') {
    cameraPrimarySourceId = nextSourceId;
    resetCameraRenderedFrame(nextSourceId, { reason: reason || '기본 카메라의 새 프레임을 기다리고 있습니다.' });
  } else {
    cameraSecondarySourceId = nextSourceId;
    resetCameraSlotRenderedFrame(slot, nextSourceId, reason || '보조 카메라의 새 프레임을 기다리고 있습니다.');
  }
  return true;
}

function applyCameraCatalog(payload) {
  const normalized = normalizeCameraCatalog(payload);
  cameraCatalog = normalized.sources;
  cameraMaxActive = normalized.maxActive;
  const primaryId = preferredCameraSource(cameraCatalog, cameraPrimarySourceId);
  const secondaryId = secondaryCameraSource(cameraCatalog, primaryId);
  setCameraSlotSource('primary', primaryId);
  setCameraSlotSource('secondary', secondaryId);
  for (const slot of Object.values(getCameraSlots())) slot.statusMeta = cameraSourceForId(slot.sourceId);
  renderCameraCatalogUi();
  syncCameraTransport();
  return normalized;
}

async function refreshCameraCatalog() {
  const generation = ++cameraCatalogRequestGeneration;
  try {
    const payload = await api('/api/v1/cameras');
    if (generation !== cameraCatalogRequestGeneration) return null;
    return applyCameraCatalog(payload);
  } catch (error) {
    if (generation !== cameraCatalogRequestGeneration) return null;
    if (!cameraCatalog.length) {
      ui.cameraCapacity.textContent = 'CAMERA API WAITING';
      ui.cameraEmptyText.textContent = `카메라 목록을 불러오지 못했습니다: ${error.message}`;
    }
    return null;
  }
}

function setCameraViewMode(mode, { persist = true } = {}) {
  const next = mode === 'dual' && cameraMaxActive >= 2 && cameraCatalog.length >= 2 ? 'dual' : 'single';
  if (cameraViewMode === next) {
    renderCameraCatalogUi();
    syncCameraTransport();
    return;
  }
  cameraViewMode = next;
  renderCameraCatalogUi();
  syncCameraTransport();
  if (persist) persistCameraPreferences();
}

function selectPrimaryCamera(sourceId, { persist = true } = {}) {
  const next = preferredCameraSource(cameraCatalog, sourceId);
  if (!next || next === cameraPrimarySourceId) return;
  const nextSecondary = secondaryCameraSource(cameraCatalog, next);
  setCameraSlotSource('primary', next, '기본 카메라를 변경하여 새 프레임을 기다리고 있습니다.');
  setCameraSlotSource('secondary', nextSecondary, '보조 카메라가 자동으로 변경되었습니다.');
  renderCameraCatalogUi();
  syncCameraTransport();
  if (persist) persistCameraPreferences();
}

function initializeCameraStreams() {
  const preferences = loadCameraPreferences();
  cameraViewMode = preferences.viewMode;
  cameraPrimarySourceId = preferences.primarySourceId;
  getCameraSlots();
  return refreshCameraCatalog();
}

function cameraFrameIsFresh(lastFrameAt, metadata = {}, now = Date.now(), maxAgeMs = CAMERA_FRAME_FRESH_MS) {
  const localAgeMs = Number(now) - Number(lastFrameAt || 0);
  if (!lastFrameAt || !Number.isFinite(localAgeMs) || localAgeMs < 0 || localAgeMs > maxAgeMs) return false;
  const state = String(metadata?.state || '').toLowerCase();
  if (state && state !== 'ok' && state !== 'live') return false;
  const reportedAge = Number(metadata?.age_s);
  if (metadata?.age_s != null && (!Number.isFinite(reportedAge) || reportedAge * 1000 > maxAgeMs)) return false;
  return true;
}

function createLatestCameraFrameQueue({ decode, render, close, onError = () => {} }) {
  let generation = 0;
  let active = false;
  let pending = null;

  async function drain(initialFrame) {
    let frame = initialFrame;
    while (frame) {
      let decoded = null;
      try {
        decoded = await decode(frame);
        if (frame.generation === generation) render(decoded, frame);
      } catch (error) {
        if (frame.generation === generation) onError(error, frame);
      } finally {
        if (decoded) close(decoded, frame);
      }
      frame = pending;
      pending = null;
    }
    active = false;
  }

  return Object.freeze({
    enqueue(frame) {
      const tagged = { ...frame, generation };
      if (active) {
        // Keep only the newest undecoded frame. ArrayBuffer payloads require no
        // explicit close and are released when this reference is replaced.
        pending = tagged;
      } else {
        active = true;
        void drain(tagged);
      }
      return generation;
    },
    reset() {
      generation += 1;
      pending = null;
      return generation;
    },
    snapshot() {
      return { generation, active, pending: pending ? 1 : 0 };
    },
  });
}

function getCameraImageDecodeQueue() {
  return getCameraSlotImageDecodeQueue(primaryCameraSlot());
}

async function decodeCameraImageFrame(frame) {
  const blob = new Blob(
    [frame.data],
    { type: frame.format === 'png' ? 'image/png' : 'image/jpeg' },
  );
  if (typeof window.createImageBitmap === 'function') {
    try {
      const bitmap = await window.createImageBitmap(blob);
      return {
        source: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        close: () => bitmap.close?.(),
      };
    } catch (_) {
      // Some Safari releases expose createImageBitmap but reject camera JPEG
      // blobs. Continue through the HTMLImageElement decoder in that case.
    }
  }

  // Safari versions without createImageBitmap still decode JPEG reliably via
  // HTMLImageElement. Object URLs live only until the frame has been drawn.
  const objectUrl = URL.createObjectURL(blob);
  const image = new window.Image();
  image.decoding = 'async';
  image.src = objectUrl;
  try {
    await image.decode();
  } catch (error) {
    URL.revokeObjectURL(objectUrl);
    throw error;
  }
  return {
    source: image,
    width: image.naturalWidth,
    height: image.naturalHeight,
    close: () => URL.revokeObjectURL(objectUrl),
  };
}

function getCameraSlotImageDecodeQueue(slot = primaryCameraSlot()) {
  if (slot.imageDecodeQueue) return slot.imageDecodeQueue;
  slot.imageDecodeQueue = createLatestCameraFrameQueue({
    decode: decodeCameraImageFrame,
    render: (decoded, frame) => renderCameraSourceFrame(
      decoded.source,
      decoded.width,
      decoded.height,
      frame.sourceKey,
      slot,
    ),
    close: (decoded) => decoded.close(),
    onError: (error) => console.warn(`${slot.role} camera image decode:`, error),
  });
  if (slot.role === 'primary') cameraImageDecodeQueue = slot.imageDecodeQueue;
  return slot.imageDecodeQueue;
}

function resetCameraImageDecodeQueue(slot = primaryCameraSlot()) {
  slot.imageDecodeQueue?.reset();
  if (slot.role === 'primary') cameraImageDecodeQueue = slot.imageDecodeQueue;
}

function enqueueCameraImageFrame(data, metadata, slot = primaryCameraSlot()) {
  getCameraSlotImageDecodeQueue(slot).enqueue({
    data,
    format: metadata.format || 'jpeg',
    seq: metadata.seq,
    sourceKey: metadata.source_id || metadata.topic || metadata.source || metadata.stream_url || metadata.transport || slot.activeSourceKey,
  });
}

function cameraFrameAvailable(now = Date.now()) {
  return cameraSlotFrameAvailable(primaryCameraSlot(), now);
}

function cameraRecordingSupported() {
  return typeof ui.cameraCanvas?.captureStream === 'function' && typeof window.MediaRecorder === 'function';
}

function setCameraMediaMessage(status, help, error = false) {
  ui.cameraMediaStatus.textContent = status;
  ui.cameraMediaStatus.dataset.state = error ? 'error' : 'ok';
  if (help) ui.cameraMediaHelp.textContent = help;
}

function syncCameraMediaControls() {
  const hasFrame = cameraFrameAvailable();
  const recording = Boolean(cameraRecording);
  const stopping = Boolean(cameraRecording?.stopping);
  const supported = cameraRecordingSupported();
  ui.cameraCaptureButton.disabled = !hasFrame;
  ui.cameraCaptureFormat.disabled = !hasFrame || recording;
  ui.cameraRecordButton.disabled = !hasFrame || recording || !supported;
  ui.cameraStopRecordButton.disabled = !recording || stopping;
  ui.cameraCanvas.closest('.camera-panel')?.classList.toggle('is-recording', recording && !stopping);
}

function syncCameraFrameFreshness(now = Date.now()) {
  const primary = primaryCameraSlot();
  const fresh = cameraFrameAvailable(now);
  syncCameraMediaControls();
  for (const slot of Object.values(getCameraSlots())) {
    renderCameraSlotIdentity(slot, now);
    if (slot.role === 'secondary' && slot.lastFrameAt && !cameraSlotFrameAvailable(slot, now)) {
      slot.empty.style.display = '';
      slot.emptyText.textContent = `마지막 영상 프레임이 ${Math.max(0, (now - slot.lastFrameAt) / 1000).toFixed(1)}초 전입니다.`;
    }
  }
  if (fresh || !primary.lastFrameAt) return fresh;
  const reportedState = String(cameraStatusMeta?.state || cameraMeta?.state || 'stale').toUpperCase();
  const message = `PRIMARY 마지막 영상 프레임이 ${Math.max(0, (now - primary.lastFrameAt) / 1000).toFixed(1)}초 전입니다. 새 프레임을 기다리고 있습니다.`;
  if (cameraRecording) {
    if (!cameraRecording.stopping) {
      stopCameraRecording({ discard: false, reason: '영상 신호가 3초 이상 멈춰 녹화를 종료하고 저장했습니다.' });
    }
  } else {
    setCameraMediaMessage(`FRAME ${reportedState === 'OK' ? 'STALE' : reportedState}`, message, true);
  }
  return false;
}

function markCameraSlotFrameRendered(slot, sourceKey = '') {
  const wasFresh = cameraSlotFrameAvailable(slot);
  if (sourceKey) slot.activeSourceKey = sourceKey;
  slot.lastFrameAt = Date.now();
  slot.frames += 1;
  slot.frameWindow.push(performance.now());
  while (slot.frameWindow.length && performance.now() - slot.frameWindow[0] > 1000) slot.frameWindow.shift();
  slot.empty.style.display = 'none';
  renderCameraSlotIdentity(slot);
  return wasFresh;
}

function markCameraFrameRendered(sourceKey = '') {
  const slot = primaryCameraSlot();
  const wasFresh = cameraFrameAvailable();
  markCameraSlotFrameRendered(slot, sourceKey);
  if (sourceKey) cameraActiveSourceKey = sourceKey;
  cameraLastFrameAt = slot.lastFrameAt;
  cameraFrames = slot.frames;
  cameraFrameWindow = slot.frameWindow;
  if (!cameraRecording && !wasFresh) {
    const recorderNote = cameraRecordingSupported()
      ? '현재 표시 프레임을 캡처하거나 브라우저에서 녹화할 수 있습니다.'
      : '화면 캡처 가능 · 이 브라우저는 영상 녹화를 지원하지 않습니다.';
    setCameraMediaMessage('FRAME READY', recorderNote);
  }
  syncCameraMediaControls();
}

// Every camera transport ends here.  A direct Flask/MJPEG adapter can pass its
// HTMLImageElement to this function and gets the same capture/record behavior
// as the existing ROS/WebSocket H.264, JPEG, PNG and raw-image paths.
function renderCameraSourceFrame(source, requestedWidth = 0, requestedHeight = 0, sourceKey = '', slot = primaryCameraSlot()) {
  const width = Number(requestedWidth || source?.displayWidth || source?.videoWidth || source?.naturalWidth || source?.width || 0);
  const height = Number(requestedHeight || source?.displayHeight || source?.videoHeight || source?.naturalHeight || source?.height || 0);
  if (!source || !Number.isFinite(width) || !Number.isFinite(height) || width < 2 || height < 2) {
    throw new Error('카메라 프레임 크기가 비어 있습니다.');
  }
  const canvas = slot.canvas;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  canvas.getContext('2d').drawImage(source, 0, 0, width, height);
  if (slot.role === 'primary') {
    markCameraFrameRendered(sourceKey || cameraMeta?.topic || cameraActiveSourceKey);
  } else {
    markCameraSlotFrameRendered(slot, sourceKey || slot.meta?.source_id || slot.meta?.topic || slot.activeSourceKey);
  }
}

function cameraTimestamp() {
  const value = new Date();
  const parts = [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, '0'),
    String(value.getDate()).padStart(2, '0'),
    '_',
    String(value.getHours()).padStart(2, '0'),
    String(value.getMinutes()).padStart(2, '0'),
    String(value.getSeconds()).padStart(2, '0'),
  ];
  return parts.join('');
}

function cameraDownloadName(kind, extension, sourceOverride = '') {
  const source = String(sourceOverride || cameraMeta?.topic || cameraActiveSourceKey || 'camera')
    .split('/').filter(Boolean).pop()?.replace(/[^a-z0-9_-]+/gi, '_') || 'camera';
  return `${source}_${kind}_${cameraTimestamp()}.${extension}`;
}

function downloadCameraBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1200);
}

async function captureCameraFrame() {
  if (!cameraFrameAvailable()) {
    const message = '캡처할 카메라 프레임이 없습니다. 영상이 표시된 뒤 다시 시도하세요.';
    setCameraMediaMessage('NO FRAME', message, true);
    showToast(message, true);
    return;
  }
  const mimeType = ui.cameraCaptureFormat.value === 'image/jpeg' ? 'image/jpeg' : 'image/png';
  const extension = mimeType === 'image/jpeg' ? 'jpg' : 'png';
  try {
    const blob = await new Promise((resolve, reject) => {
      ui.cameraCanvas.toBlob(
        (result) => result ? resolve(result) : reject(new Error('브라우저가 이미지 파일을 만들지 못했습니다.')),
        mimeType,
        mimeType === 'image/jpeg' ? 0.92 : undefined,
      );
    });
    const filename = cameraDownloadName('capture', extension);
    downloadCameraBlob(blob, filename);
    setCameraMediaMessage('CAPTURE SAVED', `${filename} 다운로드를 시작했습니다.`);
    showToast(`카메라 화면을 ${extension.toUpperCase()}로 저장했습니다.`);
  } catch (error) {
    const message = `화면 캡처 실패: ${error.message}`;
    setCameraMediaMessage('CAPTURE FAILED', message, true);
    showToast(message, true);
  }
}

function chooseCameraRecordingMimeType() {
  const candidates = [
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp8',
    'video/webm',
    'video/mp4;codecs=avc1.42E01E',
    'video/mp4',
  ];
  if (typeof window.MediaRecorder?.isTypeSupported !== 'function') return '';
  return candidates.find((mimeType) => window.MediaRecorder.isTypeSupported(mimeType)) || '';
}

function updateCameraRecordingDuration(session = cameraRecording) {
  if (!session || session.finalized) return;
  const elapsedMs = Math.max(0, performance.now() - session.startedAt);
  const seconds = Math.floor(elapsedMs / 1000);
  const minutes = Math.floor(seconds / 60);
  ui.cameraRecordDuration.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  ui.cameraRecordDuration.dateTime = `PT${seconds}S`;
  if (elapsedMs >= CAMERA_RECORD_MAX_MS && !session.stopping) {
    stopCameraRecording({ discard: false, reason: '최대 녹화 시간 10분에 도달하여 자동 저장했습니다.' });
  }
}

function finalizeCameraRecording(session) {
  if (!session || session.finalized) return;
  session.finalized = true;
  clearInterval(session.timer);
  session.stream.getTracks().forEach((track) => track.stop());
  if (cameraRecording === session) cameraRecording = null;
  syncCameraMediaControls();

  if (session.discard) {
    const message = session.reason || '녹화를 중단하고 임시 데이터를 정리했습니다.';
    setCameraMediaMessage(session.failed ? 'RECORDING FAILED' : 'RECORDING STOPPED', message, session.failed);
    if (session.failed && !session.silent) showToast(message, true);
    return;
  }
  const mimeType = session.recorder.mimeType || session.mimeType || 'video/webm';
  const blob = new Blob(session.chunks, { type: mimeType });
  if (!blob.size) {
    const message = '녹화된 프레임이 없어 파일을 만들지 못했습니다.';
    setCameraMediaMessage('EMPTY RECORDING', message, true);
    showToast(message, true);
    return;
  }
  const extension = mimeType.includes('mp4') ? 'mp4' : 'webm';
  const filename = cameraDownloadName('recording', extension, session.sourceKey);
  downloadCameraBlob(blob, filename);
  setCameraMediaMessage('RECORDING SAVED', session.reason || `${filename} 다운로드를 시작했습니다.`);
  showToast(session.reason || `카메라 녹화를 ${extension.toUpperCase()}로 저장했습니다.`);
}

function startCameraRecording() {
  if (cameraRecording) return;
  if (!cameraFrameAvailable()) {
    const message = '녹화할 카메라 프레임이 없습니다. 영상이 표시된 뒤 다시 시도하세요.';
    setCameraMediaMessage('NO FRAME', message, true);
    showToast(message, true);
    return;
  }
  if (!cameraRecordingSupported()) {
    const message = '이 브라우저는 canvas.captureStream 또는 MediaRecorder를 지원하지 않습니다.';
    setCameraMediaMessage('RECORDING UNSUPPORTED', message, true);
    showToast(message, true);
    return;
  }

  let stream = null;
  try {
    stream = ui.cameraCanvas.captureStream(30);
    if (!stream.getVideoTracks().length) throw new Error('캔버스 비디오 트랙을 만들지 못했습니다.');
    const mimeType = chooseCameraRecordingMimeType();
    let recorder;
    try {
      recorder = mimeType
        ? new window.MediaRecorder(stream, { mimeType, videoBitsPerSecond: 4_000_000 })
        : new window.MediaRecorder(stream);
    } catch (_) {
      recorder = new window.MediaRecorder(stream);
    }
    const session = {
      recorder,
      stream,
      mimeType,
      chunks: [],
      bytes: 0,
      startedAt: performance.now(),
      sourceKey: cameraActiveSourceKey,
      timer: null,
      stopping: false,
      discard: false,
      reason: '',
      failed: false,
      silent: false,
      finalized: false,
    };
    recorder.addEventListener('dataavailable', (event) => {
      if (session.discard || !event.data?.size) return;
      session.chunks.push(event.data);
      session.bytes += event.data.size;
      if (session.bytes >= CAMERA_RECORD_MAX_BYTES && !session.stopping) {
        stopCameraRecording({ discard: false, reason: '녹화 데이터가 256 MiB 제한에 도달하여 자동 저장했습니다.' });
      }
    });
    recorder.addEventListener('error', (event) => {
      if (session.stopping) return;
      session.discard = true;
      session.failed = true;
      session.reason = `브라우저 녹화 오류: ${event.error?.message || '알 수 없는 오류'}`;
      if (recorder.state !== 'inactive') recorder.stop(); else finalizeCameraRecording(session);
    });
    recorder.addEventListener('stop', () => finalizeCameraRecording(session), { once: true });
    cameraRecording = session;
    recorder.start(1000);
    session.timer = setInterval(() => updateCameraRecordingDuration(session), 250);
    updateCameraRecordingDuration(session);
    setCameraMediaMessage('RECORDING', '표시 중인 캔버스를 녹화합니다 · 최대 10분 또는 256 MiB');
    syncCameraMediaControls();
  } catch (error) {
    stream?.getTracks().forEach((track) => track.stop());
    cameraRecording = null;
    const message = `녹화 시작 실패: ${error.message}`;
    setCameraMediaMessage('RECORDING FAILED', message, true);
    syncCameraMediaControls();
    showToast(message, true);
  }
}

function cameraRecordingCleanupPolicy(trigger) {
  if (trigger === 'page_hidden') {
    return { discard: true, reason: '페이지를 벗어나 녹화를 중단하고 임시 데이터를 정리했습니다.', silent: true };
  }
  if (trigger === 'sensors_page_left') {
    return { discard: false, reason: 'Sensors 화면을 벗어나 녹화를 종료하고 저장했습니다.', silent: false };
  }
  return { discard: false, reason: '페이지가 숨겨져 녹화를 종료하고 저장했습니다.', silent: false };
}

function stopCameraRecording({ discard = false, reason = '', silent = false } = {}) {
  const session = cameraRecording;
  if (!session || session.stopping || session.finalized) return false;
  session.stopping = true;
  session.discard = discard;
  session.reason = reason;
  session.silent = silent;
  if (discard) {
    session.chunks.length = 0;
    session.bytes = 0;
  }
  clearInterval(session.timer);
  setCameraMediaMessage('FINALIZING', discard ? '녹화 데이터를 정리하고 있습니다.' : '녹화 파일을 마무리하고 있습니다.');
  syncCameraMediaControls();
  try {
    if (!discard && session.recorder.state === 'recording') session.recorder.requestData();
    if (session.recorder.state !== 'inactive') session.recorder.stop();
    else finalizeCameraRecording(session);
    if (discard) session.stream.getTracks().forEach((track) => track.stop());
  } catch (error) {
    session.discard = true;
    session.failed = true;
    session.reason = `녹화 종료 실패: ${error.message}`;
    finalizeCameraRecording(session);
  }
  return true;
}

function discardCameraRecordingForPageHide() {
  const session = cameraRecording;
  if (!session) return false;
  const policy = cameraRecordingCleanupPolicy('page_hidden');
  if (!session.stopping) return stopCameraRecording(policy);
  // visibilitychange may have started an asynchronous save immediately before
  // pagehide. A download cannot be trusted once the document is unloading, so
  // convert that in-flight finalization to a discard and release tracks now.
  session.discard = true;
  session.reason = policy.reason;
  session.silent = true;
  session.chunks.length = 0;
  session.bytes = 0;
  session.stream.getTracks().forEach((track) => track.stop());
  return true;
}

function resetCameraSlotRenderedFrame(slot, nextSourceKey = '', reason = '') {
  resetCameraImageDecodeQueue(slot);
  if (slot.videoDecoder && slot.videoDecoder.state !== 'closed') {
    try { slot.videoDecoder.close(); } catch (_) {}
  }
  slot.videoDecoder = null;
  slot.hasKey = false;
  slot.meta = null;
  slot.lastFrameAt = 0;
  slot.frames = 0;
  slot.frameWindow = [];
  slot.activeSourceKey = nextSourceKey;
  slot.canvas.width = 1;
  slot.canvas.height = 1;
  slot.empty.style.display = '';
  slot.emptyText.textContent = reason || '새 카메라 영상 신호를 기다리고 있습니다.';
  renderCameraSlotIdentity(slot);
}

function resetCameraRenderedFrame(nextSourceKey = '', { discardRecording = false, reason = '' } = {}) {
  if (cameraRecording) {
    stopCameraRecording({
      discard: discardRecording,
      reason: reason || (discardRecording ? '페이지를 벗어나 녹화를 중단했습니다.' : '카메라 소스 변경으로 녹화를 종료하고 저장했습니다.'),
      silent: discardRecording,
    });
  }
  const slot = primaryCameraSlot();
  resetCameraSlotRenderedFrame(slot, nextSourceKey, reason);
  videoDecoder = null;
  cameraHasKey = false;
  cameraMeta = null;
  cameraStatusMeta = null;
  cameraLastFrameAt = 0;
  cameraFrames = 0;
  cameraFrameWindow = slot.frameWindow;
  cameraActiveSourceKey = nextSourceKey;
  ui.cameraRecordDuration.textContent = '00:00';
  ui.cameraRecordDuration.dateTime = 'PT0S';
  if (!cameraRecording) setCameraMediaMessage('PRIMARY FRAME WAITING', 'PRIMARY 영상이 표시되면 캡처와 녹화를 사용할 수 있습니다.');
  syncCameraMediaControls();
}

function noteCameraSource(sourceKey) {
  const nextSourceKey = String(sourceKey || '').trim();
  if (!nextSourceKey) return;
  if (cameraActiveSourceKey && cameraActiveSourceKey !== nextSourceKey) {
    resetCameraRenderedFrame(nextSourceKey, { reason: '카메라 소스가 변경되어 새 프레임을 기다리고 있습니다.' });
  } else {
    cameraActiveSourceKey = nextSourceKey;
  }
}

function initializeCameraMediaControls() {
  syncCameraMediaControls();
  if (!cameraRecordingSupported()) {
    ui.cameraMediaHelp.textContent = 'PRIMARY 화면 캡처 가능 · 녹화는 canvas.captureStream 및 MediaRecorder 지원 브라우저가 필요합니다.';
  }
}

window.RobotScopeCameraFrame = Object.freeze({
  beginSource: noteCameraSource,
  draw: renderCameraSourceFrame,
  markRendered: markCameraFrameRendered,
});

function resetDecoder(slot = primaryCameraSlot()) {
  if (slot.videoDecoder && slot.videoDecoder.state !== 'closed') {
    try { slot.videoDecoder.close(); } catch (_) {}
  }
  slot.hasKey = false;
  if (slot.role === 'primary') cameraHasKey = false;
  if (!('VideoDecoder' in window)) {
    slot.emptyText.textContent = '이 브라우저는 H.264 WebCodecs를 지원하지 않습니다.';
    return false;
  }
  slot.videoDecoder = new VideoDecoder({
    output: (frame) => renderVideoFrame(frame, slot),
    error: (error) => {
      console.warn(`${slot.role} H264 decoder:`, error);
      slot.hasKey = false;
      if (slot.role === 'primary') cameraHasKey = false;
    },
  });
  slot.videoDecoder.configure({ codec: slot.meta?.encoding || 'avc1.42E01E', optimizeForLatency: true });
  if (slot.role === 'primary') videoDecoder = slot.videoDecoder;
  return true;
}

function renderVideoFrame(frame, slot = primaryCameraSlot()) {
  try {
    if (slot.role === 'primary') renderCameraSourceFrame(frame, frame.displayWidth, frame.displayHeight);
    else renderCameraSourceFrame(frame, frame.displayWidth, frame.displayHeight, slot.activeSourceKey, slot);
  } finally {
    frame.close();
  }
}

function renderImageBlob(data, metadata, slot = primaryCameraSlot()) {
  if (slot.role === 'primary') enqueueCameraImageFrame(data, metadata);
  else enqueueCameraImageFrame(data, metadata, slot);
}

function renderRawImage(data, metadata, slot = primaryCameraSlot()) {
  const { width, height, encoding, step } = metadata;
  if (!width || !height || !['rgb8', 'bgr8', 'rgba8', 'bgra8', 'mono8'].includes(encoding)) return;
  const source = new Uint8Array(data);
  const canvas = slot.canvas;
  canvas.width = width; canvas.height = height;
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(width, height);
  const channels = encoding === 'mono8' ? 1 : encoding.includes('rgba') ? 4 : 3;
  const rowStep = step || width * channels;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const src = y * rowStep + x * channels;
      const dst = (y * width + x) * 4;
      if (channels === 1) image.data[dst] = image.data[dst + 1] = image.data[dst + 2] = source[src];
      else {
        const bgr = encoding.startsWith('bgr');
        image.data[dst] = source[src + (bgr ? 2 : 0)];
        image.data[dst + 1] = source[src + 1];
        image.data[dst + 2] = source[src + (bgr ? 0 : 2)];
      }
      image.data[dst + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  if (slot.role === 'primary') markCameraFrameRendered(cameraMeta?.topic || cameraActiveSourceKey);
  else markCameraSlotFrameRendered(slot, slot.meta?.source_id || slot.meta?.topic || slot.activeSourceKey);
}

function markJointsStale(force = false) {
  if (!force && Date.now() - lastJointAt <= 1200) return;
  if (jointLive || targetJointPositions || renderedJointPositions) {
    scene3d?.resetRobotJointPositions?.();
    navigationScene3d?.resetRobotJointPositions?.();
  }
  jointLive = false;
  latestBodyRpy = null;
  targetJointPositions = null;
  renderedJointPositions = null;
  poseImuAnchor = null;
  updateLiveModelBadge();
}

function applyJointSnapshot(snapshot) {
  if (!robotRuntimeDataCompatible || selectedRobotType !== 'go2') {
    if (jointLive || targetJointPositions || renderedJointPositions) markJointsStale(true);
    return;
  }
  const positions = snapshot?.position_rad;
  const validPositions = snapshot?.state === 'ok' && Array.isArray(positions) && positions.length === 12 && positions.every(Number.isFinite);
  if (!validPositions) {
    if (snapshot?.state === 'stale') markJointsStale(true);
    return;
  }
  lastJointAt = Date.now();
  jointLive = true;
  targetJointPositions = positions.slice();
  if (!renderedJointPositions) renderedJointPositions = positions.slice();
  const rpy = snapshot?.imu_rpy_rad;
  if (Array.isArray(rpy) && rpy.length === 3 && rpy.every(Number.isFinite)) {
    latestBodyRpy = rpy.slice(0, 3);
    // FAST-LIO starts camera_init yaw at zero and does not consume Unitree's
    // absolute IMU quaternion.  Only use the high-rate IMU yaw *delta* from
    // the latest Odometry anchor; the mapped roll/pitch/yaw basis remains the
    // full FAST-LIO quaternion.
    if (targetPose && poseImuAnchor) {
      targetPose = {
        ...targetPose,
        yaw: poseImuAnchor.odomYaw + angleDelta(rpy[2], poseImuAnchor.imuYaw),
      };
    }
  }
  updateLiveModelBadge();
}

function connectJoints() {
  if (jointSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(jointSocket.readyState)) return;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  jointSocket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/joints`);
  jointSocket.onmessage = (event) => {
    try { applyJointSnapshot(JSON.parse(event.data)); }
    catch (error) { console.warn('joint stream:', error); }
  };
  jointSocket.onclose = () => setTimeout(connectJoints, 1400);
  jointSocket.onerror = () => jointSocket.close();
}

function connectPose() {
  if (poseSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(poseSocket.readyState)) return;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  poseSocket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/pose`);
  poseSocket.onmessage = (event) => {
    try { applyPoseSnapshot(JSON.parse(event.data)); }
    catch (error) { console.warn('pose stream:', error); }
  };
  poseSocket.onclose = () => setTimeout(connectPose, 1200);
  poseSocket.onerror = () => poseSocket.close();
}

function cameraTransportWanted() {
  return activePage === 'sensors' && !document.hidden;
}

function cameraSlotTransportWanted(slot) {
  if (!cameraTransportWanted() || !slot.sourceId) return false;
  if (slot.role === 'secondary' && cameraViewMode !== 'dual') return false;
  const source = cameraSourceForId(slot.sourceId);
  return source?.available !== false;
}

function disconnectCameraSlot(slot) {
  slot.socketGeneration += 1;
  clearTimeout(slot.reconnectTimer);
  slot.reconnectTimer = 0;
  const socket = slot.socket;
  slot.socket = null;
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) {
    socket.close(1000, 'camera view inactive');
  }
  resetCameraImageDecodeQueue(slot);
  if (slot.videoDecoder && slot.videoDecoder.state !== 'closed') {
    try { slot.videoDecoder.close(); } catch (_) {}
  }
  slot.videoDecoder = null;
  slot.hasKey = false;
  slot.meta = null;
  slot.lastFrameAt = 0;
  slot.empty.style.display = '';
  slot.emptyText.textContent = slot.sourceId ? '카메라 스트림 연결을 기다리고 있습니다.' : '선택된 카메라가 없습니다.';
  if (slot.role === 'primary') {
    cameraSocketGeneration = slot.socketGeneration;
    cameraReconnectTimer = 0;
    cameraSocket = null;
    videoDecoder = null;
    cameraHasKey = false;
    cameraMeta = null;
    cameraLastFrameAt = 0;
  }
  renderCameraSlotIdentity(slot);
}

function disconnectCamera() {
  for (const slot of Object.values(getCameraSlots())) disconnectCameraSlot(slot);
  syncCameraFrameFreshness();
}

function connectCameraSlot(slot) {
  if (!cameraSlotTransportWanted(slot)) return;
  if (slot.socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(slot.socket.readyState)) return;
  const generation = ++slot.socketGeneration;
  const sourceId = slot.sourceId;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/camera?source_id=${encodeURIComponent(sourceId)}`);
  slot.socket = socket;
  if (slot.role === 'primary') {
    cameraSocket = socket;
    cameraSocketGeneration = generation;
  }
  socket.binaryType = 'arraybuffer';
  socket.onopen = () => {
    if (slot.socket === socket && generation === slot.socketGeneration) renderCameraCatalogUi();
  };
  socket.onmessage = (event) => {
    if (slot.socket !== socket || generation !== slot.socketGeneration || sourceId !== slot.sourceId || !cameraSlotTransportWanted(slot)) return;
    if (typeof event.data === 'string') {
      try {
        const metadata = JSON.parse(event.data);
        const sourceKey = metadata.source_id || metadata.topic || metadata.source || metadata.stream_url || metadata.transport || sourceId;
        if (slot.role === 'primary') {
          if (!metadata.source_id) noteCameraSource(metadata.topic || metadata.source || metadata.stream_url || metadata.transport);
          cameraMeta = metadata;
          cameraActiveSourceKey = sourceKey;
        }
        slot.meta = { ...metadata, source_id: metadata.source_id || sourceId };
        slot.activeSourceKey = sourceKey;
        renderCameraSlotIdentity(slot);
      } catch (error) {
        console.warn(`${slot.role} camera metadata:`, error);
      }
      return;
    }
    if (!slot.meta) return;
    const metadata = { format: 'jpeg', ...slot.meta };
    try {
      if (metadata.format === 'h264') {
        if (!slot.videoDecoder || slot.videoDecoder.state === 'closed') if (!resetDecoder(slot)) return;
        if (metadata.key) slot.hasKey = true;
        if (!slot.hasKey) return;
        if (slot.role === 'primary') cameraHasKey = slot.hasKey;
        const chunk = new EncodedVideoChunk({
          type: metadata.key ? 'key' : 'delta',
          timestamp: Number(metadata.seq) * 33333,
          data: new Uint8Array(event.data),
        });
        if (slot.videoDecoder.decodeQueueSize < 4) slot.videoDecoder.decode(chunk);
      } else if (metadata.format === 'jpeg' || metadata.format === 'png') {
        renderImageBlob(event.data, metadata, slot);
      } else if (metadata.format === 'raw') {
        renderRawImage(event.data, metadata, slot);
      }
    } catch (error) {
      console.warn(`${slot.role} camera render:`, error);
      if (metadata.format === 'h264') resetDecoder(slot);
    }
  };
  socket.onclose = () => {
    if (slot.socket !== socket || generation !== slot.socketGeneration) return;
    slot.socket = null;
    if (slot.role === 'primary') cameraSocket = null;
    resetCameraImageDecodeQueue(slot);
    if (slot.videoDecoder && slot.videoDecoder.state !== 'closed') {
      try { slot.videoDecoder.close(); } catch (_) {}
    }
    slot.videoDecoder = null;
    slot.hasKey = false;
    renderCameraCatalogUi();
    if (cameraSlotTransportWanted(slot)) {
      slot.reconnectTimer = setTimeout(() => {
        slot.reconnectTimer = 0;
        if (slot.role === 'primary') cameraReconnectTimer = 0;
        connectCameraSlot(slot);
      }, 1800);
      if (slot.role === 'primary') cameraReconnectTimer = slot.reconnectTimer;
    }
  };
  socket.onerror = () => socket.close();
}

function connectCamera() {
  for (const slot of Object.values(getCameraSlots())) connectCameraSlot(slot);
}

function syncCameraTransport() {
  for (const slot of Object.values(getCameraSlots())) {
    if (cameraSlotTransportWanted(slot)) connectCameraSlot(slot);
    else if (slot.socket || slot.reconnectTimer) disconnectCameraSlot(slot);
  }
}

// Read-only browser hooks make on-device stream diagnostics possible without
// exposing mutable WebSocket or decoder objects to the console.
window.RobotScopeCameraStreams = Object.freeze({
  normalizeCatalog: normalizeCameraCatalog,
  chooseSecondary: secondaryCameraSource,
  createLatestFrameQueue: createLatestCameraFrameQueue,
  refresh: refreshCameraCatalog,
  selectPrimary: selectPrimaryCamera,
  setViewMode: setCameraViewMode,
  snapshot() {
    const slots = Object.fromEntries(Object.entries(getCameraSlots()).map(([role, slot]) => [role, {
      sourceId: slot.sourceId,
      connected: slot.socket?.readyState === WebSocket.OPEN,
      socketGeneration: slot.socketGeneration,
      queue: slot.imageDecodeQueue?.snapshot() || null,
      lastFrameAt: slot.lastFrameAt,
      fresh: cameraSlotFrameAvailable(slot),
    }]));
    return {
      viewMode: cameraViewMode,
      maxActive: cameraMaxActive,
      sources: cameraCatalog.map((source) => ({ ...source })),
      slots,
    };
  },
});

function controlReady(snapshot = controlSnapshot) {
  if (window.RobotProfiles?.profileSupports?.(activeRobotProfile(), 'manual_control') !== true) return false;
  const available = snapshot?.available ?? snapshot?.ready;
  return Boolean(snapshot?.enabled && snapshot?.configured && available);
}

function controlEstopLatched(snapshot = controlSnapshot) {
  return Boolean(snapshot?.estop_latched ?? snapshot?.estop?.latched);
}

function controlLimits() {
  const limits = controlSnapshot?.limits || {};
  return {
    max_linear_x: Math.max(0, Number(limits.max_linear_x ?? limits.vx_mps) || 0),
    max_linear_y: Math.max(0, Number(limits.max_linear_y ?? limits.vy_mps) || 0),
    max_angular_z: Math.max(0, Number(limits.max_angular_z ?? limits.wz_rps) || 0),
  };
}

function extractControlSnapshot(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.control && typeof payload.control === 'object') return payload.control;
  if (Object.hasOwn(payload, 'enabled') && Object.hasOwn(payload, 'lease')) return payload;
  if (payload.snapshot && typeof payload.snapshot === 'object') return extractControlSnapshot(payload.snapshot);
  return null;
}

function actionList(snapshot = controlSnapshot) {
  const actions = snapshot?.actions;
  if (Array.isArray(actions)) return actions;
  if (actions && typeof actions === 'object') {
    return Object.entries(actions).map(([id, metadata]) => ({ id, ...(metadata || {}) }));
  }
  return [];
}

function normalizedBridgeState() {
  const bridge = controlSnapshot?.bridge || {};
  const state = String(bridge.state || (bridge.connected ? 'connected' : bridge.available ? 'ready' : 'waiting'));
  const ready = Boolean(bridge.connected || bridge.available || ['ready', 'connected', 'online', 'ok'].includes(state.toLowerCase()));
  return { bridge, state, ready };
}

function syncEstopClearButton() {
  const manualControlSupported = window.RobotProfiles?.profileSupports?.(activeRobotProfile(), 'manual_control') === true;
  controlUi.clear.disabled = !manualControlSupported || controlEmergencyBusy || !controlEstopLatched() || !controlUi.clearConfirm.checked;
}

function renderControlStatus() {
  const snapshot = controlSnapshot || {};
  const manualControlSupported = window.RobotProfiles?.profileSupports?.(activeRobotProfile(), 'manual_control') === true;
  const ready = controlReady(snapshot);
  const estopLatched = controlEstopLatched(snapshot);
  const serverLease = snapshot.lease || {};
  const locallyArmed = Boolean(controlLeaseId);
  const navigationBlocking = navigationActivityBlocksManualControl();
  const { bridge, state: bridgeState, ready: bridgeReady } = normalizedBridgeState();
  const availabilityCard = controlUi.availability.closest('.control-status-card');
  const leaseCard = controlUi.leaseState.closest('.control-status-card');
  const bridgeCard = controlUi.bridgeState.closest('.control-status-card');

  availabilityCard.classList.toggle('is-ok', ready);
  availabilityCard.classList.toggle('is-error', !manualControlSupported || snapshot.enabled === false || snapshot.configured === false);
  controlUi.availability.textContent = !manualControlSupported ? 'UNSUPPORTED' : ready ? 'AVAILABLE' : snapshot.enabled === false ? 'DISABLED' : snapshot.configured === false ? 'NOT CONFIGURED' : 'UNAVAILABLE';
  controlUi.availabilityNote.textContent = navigationBlocking
    ? 'Nav2 실행 중 · STOP 후 수동 제어 가능'
    : !manualControlSupported ? `${activeRobotProfile()?.label || '선택 로봇'} 제어는 아직 지원하지 않음` : snapshot.state || (ready ? '제어 서버 준비 완료' : '서버 설정 또는 로봇 연결 확인');

  leaseCard.classList.toggle('is-ok', locallyArmed && serverLease.active !== false);
  leaseCard.classList.toggle('is-error', Boolean(serverLease.active && !locallyArmed));
  controlUi.leaseState.textContent = locallyArmed ? (serverLease.bound ? 'BOUND' : 'ARMED') : serverLease.active ? 'IN USE' : 'DISARMED';
  controlUi.leaseNote.textContent = locallyArmed ? `${controlLeaseSource.toUpperCase()} · 이 브라우저` : serverLease.active ? `${String(serverLease.source || serverLease.input_source || 'other').toUpperCase()} 제어 중` : '명령 권한 없음';

  bridgeCard.classList.toggle('is-ok', manualControlSupported && bridgeReady);
  bridgeCard.classList.toggle('is-error', ['error', 'offline', 'failed'].includes(bridgeState.toLowerCase()));
  controlUi.bridgeState.textContent = bridgeState.toUpperCase();
  controlUi.bridgeNote.textContent = !manualControlSupported ? '수동 제어 지원 로봇에서만 사용' : bridge.message || bridge.detail || (bridgeReady ? 'Go2 명령 브리지 준비' : 'Go2 연결 대기');

  controlUi.estopStatusCard.classList.toggle('is-latched', estopLatched);
  controlUi.estopState.textContent = estopLatched ? 'LATCHED' : 'CLEAR';
  controlUi.estopNote.textContent = estopLatched ? '안전 확인 후 해제 필요' : '대시보드 정지 해제 상태';

  if (estopLatched) setStatePill(controlUi.statePill, 'error', 'SOFTWARE STOP');
  else if (locallyArmed) setStatePill(controlUi.statePill, 'ok', serverLease.bound ? 'ARMED · BOUND' : 'ARMED · BINDING');
  else if (navigationBlocking) setStatePill(controlUi.statePill, 'waiting', 'NAVIGATION ACTIVE');
  else setStatePill(controlUi.statePill, ready ? 'waiting' : 'error', ready ? 'DISARMED' : 'UNAVAILABLE');

  controlUi.arm.disabled = controlArmBusy || controlDisarmBusy || locallyArmed || !ready || estopLatched || navigationActivityBlocksManualControl();
  controlUi.disarm.disabled = controlDisarmBusy || !locallyArmed;
  controlUi.inputSource.setAttribute('aria-disabled', locallyArmed ? 'true' : 'false');
  controlUi.estop.disabled = controlEmergencyBusy || !manualControlSupported;
  syncEstopClearButton();
  renderControlInputMode();
  renderControlActions();
}

function renderControlInputMode() {
  const source = controlUi.inputSource.value;
  const gamepadMode = source === 'gamepad';
  const locallyArmed = Boolean(controlLeaseId);
  controlUi.gamepadWrap.classList.toggle('is-hidden', !gamepadMode);
  controlUi.keyboardGuide.classList.toggle('is-hidden', gamepadMode);
  controlUi.gamepadGuide.classList.toggle('is-hidden', !gamepadMode);
  controlUi.touchController.classList.toggle('is-hidden', gamepadMode);
  controlUi.touchController.querySelectorAll('button').forEach((button) => { button.disabled = !locallyArmed || gamepadMode; });

  if (gamepadMode) {
    const pad = selectedControlGamepad();
    controlUi.deviceIndicator.className = `device-indicator ${pad ? 'is-ok' : 'is-error'}`;
    controlUi.deviceStatus.textContent = pad ? `${pad.id} 연결됨` : '선택한 게임패드 연결 끊김';
  } else {
    controlUi.deviceIndicator.className = 'device-indicator is-ok';
    controlUi.deviceStatus.textContent = locallyArmed ? '키보드·화면 버튼 제어 활성' : '키보드 입력 준비';
  }
}

function actionNeedsConfirmation(action) {
  return Boolean(action.requires_confirmation ?? action.confirmation_required ?? action.dangerous ?? true);
}

function renderControlActions() {
  const focusedAction = document.activeElement?.dataset?.controlAction || '';
  const actions = actionList();
  if (!actions.length) {
    controlUi.actions.innerHTML = '<div class="control-action-empty">서버에서 허용한 모션이 없습니다.</div>';
    return;
  }
  const armed = Boolean(controlLeaseId) && !controlEstopLatched() && !controlHadDeadman && !controlActionBusy && !navigationActivityBlocksManualControl();
  const now = Date.now();
  if (actionConfirmation && actionConfirmation.expires <= now) actionConfirmation = null;
  controlUi.actions.innerHTML = actions.map((action) => {
    const id = String(action.action_id ?? (typeof action.id === 'string' ? action.id : action.name ?? action.id ?? ''));
    const confirming = actionConfirmation?.id === id && actionConfirmation.expires > now;
    const enabled = armed && action.enabled !== false && action.available !== false;
    const needsConfirmation = actionNeedsConfirmation(action);
    const buttonLabel = confirming ? '다시 눌러 실행 확인' : action.button_label || action.buttonLabel || '실행';
    return `<article class="control-action-card">
      <span>${escapeHtml(action.category || action.group || action.type || 'GO2 ACTION')}</span>
      <strong>${escapeHtml(action.label || action.name || id)}</strong>
      <small>${escapeHtml(action.description || action.note || '서버 허용 목록에 등록된 Go2 동작입니다.')}</small>
      <button type="button" data-control-action="${escapeHtml(id)}" data-confirm="${needsConfirmation ? 'true' : 'false'}" class="${confirming ? 'is-confirming' : ''}" ${enabled ? '' : 'disabled'}>${escapeHtml(buttonLabel)}</button>
    </article>`;
  }).join('');
  if (focusedAction) {
    requestAnimationFrame(() => {
      Array.from(controlUi.actions.querySelectorAll('[data-control-action]'))
        .find((button) => button.dataset.controlAction === focusedAction)?.focus({ preventScroll: true });
    });
  }
}

function commandNumber(value) {
  const number = Number(value) || 0;
  return `${number >= 0 ? '+' : ''}${number.toFixed(3)}`;
}

function renderControlCommand(command = controlLastCommand || controlSnapshot?.command || controlInput?.zeroCommand(controlUi.inputSource.value)) {
  if (!command) return;
  const limits = controlLimits();
  const x = Number(command.linear_x) || 0;
  const y = Number(command.linear_y) || 0;
  const z = Number(command.angular_z) || 0;
  controlUi.commandX.textContent = commandNumber(x);
  controlUi.commandY.textContent = commandNumber(y);
  controlUi.commandZ.textContent = commandNumber(z);
  controlUi.commandXBar.style.width = `${Math.min(100, Math.abs(x) / (limits.max_linear_x || 1) * 100)}%`;
  controlUi.commandYBar.style.width = `${Math.min(100, Math.abs(y) / (limits.max_linear_y || 1) * 100)}%`;
  controlUi.commandZBar.style.width = `${Math.min(100, Math.abs(z) / (limits.max_angular_z || 1) * 100)}%`;
  controlUi.deadmanState.textContent = command.deadman ? 'HELD' : 'RELEASED';
  controlUi.deadmanMonitor.classList.toggle('is-active', Boolean(command.deadman));
  controlUi.commandSource.textContent = command.deadman ? `${String(command.source || controlLeaseSource || 'input').toUpperCase()} · LIVE` : 'ZERO COMMAND';
}

function applyControlSnapshot(snapshot) {
  if (!snapshot) return;
  controlSnapshot = snapshot;
  if (!controlSpeedInitialized) {
    const percent = controlInput.clamp(Number(snapshot.limits?.default_speed_scale) || 0.3, 0.1, 1) * 100;
    controlUi.speed.value = String(Math.round(percent / 5) * 5);
    controlSpeedInitialized = true;
  }
  controlUi.speedOutput.textContent = `${controlUi.speed.value}%`;
  renderControlStatus();
  renderNavigationStatus();
  if (!controlLeaseId) renderControlCommand(snapshot.command);
}

async function refreshControlSnapshot() {
  if (!['controls', 'navigation'].includes(activePage)) return;
  // A poll started before ARM can finish afterward with the old inactive
  // snapshot. Never let that stale response revoke a newer local lease.
  const armGenerationAtRequest = controlArmGeneration;
  const leaseAtRequest = controlLeaseId;
  try {
    const snapshot = extractControlSnapshot(await api('/api/v1/control'));
    if (armGenerationAtRequest !== controlArmGeneration || leaseAtRequest !== controlLeaseId) return;
    applyControlSnapshot(snapshot);
    if (controlLeaseId && snapshot?.lease?.active === false && !controlDisarmBusy) {
      await failSafeDisarm('lease_expired', { notify: true });
    }
  } catch (error) {
    if (armGenerationAtRequest !== controlArmGeneration || leaseAtRequest !== controlLeaseId) return;
    controlUi.availability.textContent = 'API ERROR';
    controlUi.availabilityNote.textContent = error.message;
    controlUi.availability.closest('.control-status-card').classList.add('is-error');
  }
}

function selectedControlGamepad() {
  if (!navigator.getGamepads || selectedGamepadIndex === '') return null;
  return Array.from(navigator.getGamepads()).find((pad) => pad?.mapping === 'standard' && String(pad.index) === String(selectedGamepadIndex)) || null;
}

function refreshControlGamepads() {
  if (!navigator.getGamepads) return;
  const detectedPads = Array.from(navigator.getGamepads()).filter(Boolean);
  const pads = detectedPads.filter((pad) => pad.mapping === 'standard');
  const previous = selectedGamepadIndex || controlUi.gamepad.value;
  controlUi.gamepad.innerHTML = pads.length
    ? pads.map((pad) => `<option value="${pad.index}">${escapeHtml(pad.id || `Gamepad ${pad.index + 1}`)}</option>`).join('')
    : `<option value="">${detectedPads.length ? '표준 매핑 장치 없음' : '연결된 장치 없음'}</option>`;
  const stillPresent = pads.some((pad) => String(pad.index) === String(previous));
  const selectedDisconnected = previous !== '' && !stillPresent;
  selectedGamepadIndex = stillPresent ? String(previous) : pads.length ? String(pads[0].index) : '';
  controlUi.gamepad.value = selectedGamepadIndex;
  renderControlInputMode();
  if (controlLeaseId && controlLeaseSource === 'gamepad' && (selectedDisconnected || !selectedControlGamepad())) {
    failSafeDisarm('gamepad_disconnected', { notify: true });
  }
}

function controlBackpressureDecision(queuedBytes, sinceMs, nowMs) {
  if (!Number.isFinite(queuedBytes) || queuedBytes > CONTROL_SOCKET_MAX_BUFFER_BYTES) {
    return { action: 'disarm', sinceMs: null };
  }
  if (queuedBytes <= 0) return { action: 'send', sinceMs: null };
  const startedAt = Number.isFinite(sinceMs) ? sinceMs : nowMs;
  return {
    action: nowMs - startedAt >= CONTROL_SOCKET_BACKPRESSURE_GRACE_MS ? 'disarm' : 'skip',
    sinceMs: startedAt,
  };
}

function controlSocketSend(message, socket = controlSocket) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false;
  const queuedBytes = Number(socket.bufferedAmount);
  const pressure = controlBackpressureDecision(queuedBytes, controlBackpressureSince, Date.now());
  controlBackpressureSince = pressure.sinceMs;
  if (pressure.action === 'disarm') {
    if (!controlDisarmBusy) failSafeDisarm('websocket_backpressure', { notify: true });
    return false;
  }
  if (pressure.action === 'skip') {
    // Never add a newer command behind an unsent control frame. The 100 ms
    // grace absorbs normal browser flush jitter but remains below the 200 ms
    // server command watchdog.
    return false;
  }
  try { socket.send(JSON.stringify(message)); return true; }
  catch (_) {
    if (!controlDisarmBusy) failSafeDisarm('websocket_send_failed', { notify: true });
    return false;
  }
}

function clearPendingControlAction(render = true) {
  if (controlActionAckTimer) clearTimeout(controlActionAckTimer);
  controlActionAckTimer = null;
  controlActionBusy = false;
  pendingControlActionId = '';
  actionConfirmation = null;
  if (render) renderControlActions();
}

function zeroTwistMessage(leaseId = controlLeaseId, source = controlLeaseSource || controlUi.inputSource.value) {
  return {
    type: 'twist', lease_id: leaseId, seq: ++controlSequence, source,
    deadman: false, linear_x: 0, linear_y: 0, angular_z: 0,
    speed_scale: Number(controlUi.speed.value) / 100, client_time_ms: Date.now(),
  };
}

function sendImmediateZero(leaseId = controlLeaseId, source = controlLeaseSource) {
  if (!leaseId) return;
  controlSocketSend(zeroTwistMessage(leaseId, source));
  controlLastCommand = controlInput.zeroCommand(source || 'keyboard');
  renderControlCommand(controlLastCommand);
}

function closeControlSocket(reason = 'client_close') {
  const socket = controlSocket;
  controlSocket = null;
  controlSocketBound = false;
  controlBackpressureSince = null;
  clearPendingControlAction(false);
  if (!socket) return;
  intentionallyClosedControlSockets.add(socket);
  try { socket.close(1000, reason.slice(0, 90)); } catch (_) {}
}

function connectControlSocket() {
  if (activePage !== 'controls' || !controlLeaseId) return;
  if (controlSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(controlSocket.readyState)) return;
  const leaseAtConnect = controlLeaseId;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/control`);
  controlSocket = socket;
  controlSocketBound = false;
  socket.onopen = () => {
    if (activePage !== 'controls' || controlLeaseId !== leaseAtConnect) {
      intentionallyClosedControlSockets.add(socket);
      socket.close(1000, 'inactive_control_page');
      return;
    }
    controlSocketSend({ type: 'bind', lease_id: leaseAtConnect, client_time_ms: Date.now() }, socket);
    lastControlHeartbeatAt = Date.now();
  };
  socket.onmessage = (event) => {
    // Ignore late bound/error frames from a socket that belonged to an older
    // lease. They must never mutate or revoke the replacement control session.
    if (controlSocket !== socket || controlLeaseId !== leaseAtConnect) return;
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === 'error') {
        clearPendingControlAction();
        showToast(`제어 스트림 오류: ${payload.detail || payload.message || 'unknown'}`, true);
        failSafeDisarm('websocket_server_error');
        return;
      }
      if (payload.type === 'bound') {
        controlSocketBound = true;
        applyControlSnapshot(extractControlSnapshot(payload));
        return;
      }
      if (payload.type === 'action_accepted') {
        const acceptedAction = pendingControlActionId || payload.action_id || payload.action || 'Go2';
        const acceptedSnapshot = extractControlSnapshot(payload);
        controlLeaseId = '';
        controlLeaseSource = '';
        clearPendingControlAction(false);
        resetControlInputs();
        // Do not send zero/release after an accepted one-shot action: either
        // frame could cancel it. Closing the socket intentionally makes the
        // next browser command require a completely new ARM.
        closeControlSocket('action_accepted');
        if (acceptedSnapshot) {
          controlSnapshot = {
            ...acceptedSnapshot,
            lease: { ...(acceptedSnapshot.lease || {}), active: false, bound: false, source: null },
          };
        }
        renderControlStatus();
        showToast(`${acceptedAction} 대시보드 명령 접수 · 브리지 수신/실행 완료 신호가 아닙니다. 안전 대기 종료 후 다시 ARM하세요.`);
        setTimeout(() => refreshControlSnapshot(), 400);
        return;
      }
      applyControlSnapshot(extractControlSnapshot(payload));
    } catch (error) { console.warn('control stream:', error); }
  };
  socket.onerror = () => { try { socket.close(); } catch (_) {} };
  socket.onclose = () => {
    if (controlSocket === socket) {
      controlSocket = null;
      controlSocketBound = false;
    }
    if (intentionallyClosedControlSockets.has(socket)) return;
    // A lost command stream is a terminal lease event: do not auto re-arm.
    if (controlLeaseId === leaseAtConnect) failSafeDisarm('websocket_closed', { notify: true });
  };
}

function resetControlInputs() {
  controlPressedKeys.clear();
  controlPointerDirections.clear();
  controlDeadmanPointers.clear();
  controlHadDeadman = false;
  controlMotionFrameActive = false;
  document.querySelectorAll('.keyboard-guide kbd.is-pressed, .touch-dpad button.is-pressed').forEach((element) => element.classList.remove('is-pressed'));
  controlLastCommand = controlInput.zeroCommand(controlLeaseSource || controlUi.inputSource.value);
  renderControlCommand(controlLastCommand);
}

async function failSafeDisarm(reason, { notify = false } = {}) {
  if (controlDisarmBusy) return;
  const leaseId = controlLeaseId;
  const source = controlLeaseSource;
  if (!leaseId) {
    closeControlSocket(reason);
    resetControlInputs();
    renderControlStatus();
    return;
  }
  controlDisarmBusy = true;
  sendImmediateZero(leaseId, source);
  controlSocketSend({ type: 'release', lease_id: leaseId, reason, client_time_ms: Date.now() });
  controlLeaseId = '';
  controlLeaseSource = '';
  closeControlSocket(reason);
  resetControlInputs();
  renderControlStatus();
  try {
    await api('/api/v1/control/disarm', { method: 'POST', keepalive: true, body: JSON.stringify({ lease_id: leaseId }) });
    if (notify) showToast('안전 해제: 제로 명령 후 제어 권한을 반납했습니다.');
  } catch (error) {
    if (notify) showToast(`제어 해제 확인 실패: ${error.message}`, true);
  } finally {
    controlDisarmBusy = false;
    if (activePage === 'controls') await refreshControlSnapshot();
  }
}

function invalidatePendingArm() {
  controlArmGeneration += 1;
  controlArmBusy = false;
}

async function armControl() {
  if (controlLeaseId || controlDisarmBusy || controlArmBusy) return;
  if (navigationActivityBlocksManualControl()) {
    showToast('Nav2 pipeline 또는 목표가 활성 상태입니다. Navigation에서 STOP한 뒤 ARM하세요.', true);
    return;
  }
  const source = controlUi.inputSource.value;
  if (source === 'gamepad' && !selectedControlGamepad()) { showToast('연결된 게임패드를 선택하세요.', true); return; }
  const armGeneration = ++controlArmGeneration;
  controlArmBusy = true;
  renderControlStatus();
  try {
    const response = await api('/api/v1/control/arm', {
      method: 'POST', body: JSON.stringify({ input_source: source }),
    });
    if (!response.lease_id) throw new Error('서버가 lease_id를 반환하지 않았습니다.');
    if (armGeneration !== controlArmGeneration || activePage !== 'controls') {
      try {
        await api('/api/v1/control/disarm', {
          method: 'POST', keepalive: true, body: JSON.stringify({ lease_id: String(response.lease_id) }),
        });
      } catch (_) {}
      return;
    }
    controlLeaseId = String(response.lease_id);
    controlLeaseSource = source;
    controlSequence = -1;
    resetControlInputs();
    controlUi.arm.blur();
    applyControlSnapshot(extractControlSnapshot(response));
    connectControlSocket();
    renderControlStatus();
    showToast(`${source === 'gamepad' ? '게임패드' : '키보드'} 제어를 ARM했습니다. 데드맨을 계속 누르세요.`);
  } catch (error) {
    if (armGeneration === controlArmGeneration) showToast(`ARM 실패: ${error.message}`, true);
  } finally {
    if (armGeneration === controlArmGeneration) controlArmBusy = false;
    renderControlStatus();
  }
}

function currentRawControlCommand() {
  if (controlLeaseSource === 'gamepad') return controlInput.gamepadCommand(selectedControlGamepad());
  const keyboard = controlInput.keyboardCommand(controlPressedKeys);
  const pointer = controlInput.pointerCommand(
    new Set(controlPointerDirections.values()),
    controlDeadmanPointers.size > 0 || keyboard.deadman,
  );
  if (keyboard.deadman && pointer.deadman) {
    return {
      source: 'keyboard', deadman: true,
      linear_x: controlInput.clamp(keyboard.linear_x + pointer.linear_x),
      linear_y: controlInput.clamp(keyboard.linear_y + pointer.linear_y),
      angular_z: controlInput.clamp(keyboard.angular_z + pointer.angular_z),
    };
  }
  return keyboard.deadman ? keyboard : pointer;
}

function controlTick() {
  if (activePage !== 'controls') return;
  const estopPad = controlUi.inputSource.value === 'gamepad' ? selectedControlGamepad() : null;
  const estopPressed = Boolean(estopPad && controlInput.gamepadButtonPressed(estopPad, 1));
  if (estopPressed && !gamepadEstopPressed) {
    gamepadEstopPressed = true;
    triggerEmergencyStop('gamepad_b');
    return;
  }
  gamepadEstopPressed = estopPressed;
  if (!controlLeaseId || controlActionBusy) return;
  if (controlLeaseSource === 'gamepad') {
    const pad = selectedControlGamepad();
    if (!pad) { failSafeDisarm('gamepad_disconnected', { notify: true }); return; }
  }
  const raw = currentRawControlCommand();
  if (controlHadDeadman && !raw.deadman) {
    failSafeDisarm('deadman_released', { notify: true });
    return;
  }
  if (raw.deadman && !controlHadDeadman) {
    controlHadDeadman = true;
    renderControlActions();
  }
  const speedScale = Number(controlUi.speed.value) / 100;
  const scaled = controlInput.scaleCommand(raw, controlLimits(), speedScale);
  controlLastCommand = scaled;
  renderControlCommand(scaled);
  if (controlSocketBound && controlSocket?.readyState === WebSocket.OPEN) {
    const frameIntent = controlInput.controlFrameIntent(raw, {
      motionActive: controlMotionFrameActive,
      heartbeatDue: Date.now() - lastControlHeartbeatAt >= 1000,
    });
    if (frameIntent === 'stop') {
      const stopped = controlSocketSend({
        type: 'twist', lease_id: controlLeaseId, seq: ++controlSequence,
        source: controlLeaseSource, deadman: false,
        linear_x: 0, linear_y: 0, angular_z: 0,
        speed_scale: speedScale, client_time_ms: Date.now(),
      });
      if (stopped) controlMotionFrameActive = false;
      return;
    }
    if (frameIntent === 'heartbeat') {
      const heartbeatSent = controlSocketSend({
        type: 'heartbeat', lease_id: controlLeaseId, seq: ++controlSequence,
        client_time_ms: Date.now(),
      });
      if (heartbeatSent) lastControlHeartbeatAt = Date.now();
      return;
    }
    if (frameIntent !== 'drive') return;
    const driven = controlSocketSend({
      type: 'twist', lease_id: controlLeaseId, seq: ++controlSequence,
      source: controlLeaseSource, deadman: raw.deadman,
      linear_x: raw.linear_x, linear_y: raw.linear_y, angular_z: raw.angular_z,
      speed_scale: speedScale, client_time_ms: Date.now(),
    });
    if (driven) controlMotionFrameActive = true;
  }
}

async function triggerEmergencyStop(reason = 'dashboard_button') {
  if (controlEmergencyBusy) return;
  invalidatePendingArm();
  controlEmergencyBusy = true;
  const leaseId = controlLeaseId;
  const source = controlLeaseSource;
  sendImmediateZero(leaseId, source);
  if (leaseId) controlSocketSend({ type: 'release', lease_id: leaseId, reason: 'software_estop', client_time_ms: Date.now() });
  controlLeaseId = '';
  controlLeaseSource = '';
  closeControlSocket('software_estop');
  resetControlInputs();
  renderControlStatus();
  try {
    await api('/api/v1/control/stop', { method: 'POST', body: JSON.stringify({ reason }) });
    if (leaseId) {
      try { await api('/api/v1/control/disarm', { method: 'POST', body: JSON.stringify({ lease_id: leaseId }) }); } catch (_) {}
    }
    showToast('대시보드 SOFTWARE STOP 명령을 전송했습니다. 물리 E-stop은 아닙니다.', true);
  } catch (error) {
    showToast(`대시보드 정지 전송 실패: ${error.message}`, true);
  } finally {
    controlEmergencyBusy = false;
    if (activePage === 'controls') await refreshControlSnapshot();
  }
}

async function clearEmergencyStop() {
  if (!controlUi.clearConfirm.checked) return;
  controlEmergencyBusy = true;
  syncEstopClearButton();
  try {
    const response = await api('/api/v1/control/estop/clear', {
      method: 'POST', body: JSON.stringify({ confirmed: true }),
    });
    controlUi.clearConfirm.checked = false;
    applyControlSnapshot(extractControlSnapshot(response));
    showToast('대시보드 SOFTWARE STOP 래치를 해제했습니다. 제어하려면 다시 ARM하세요.');
  } catch (error) {
    showToast(`대시보드 정지 해제 실패: ${error.message}`, true);
  } finally {
    controlEmergencyBusy = false;
    syncEstopClearButton();
    if (activePage === 'controls') await refreshControlSnapshot();
  }
}

function invokeControlAction(id, confirmed) {
  if (!controlLeaseId) { showToast('먼저 제어를 ARM하세요.', true); return; }
  if (controlActionBusy) return;
  if (controlHadDeadman) {
    showToast('주행에 사용한 ARM은 안전 해제 후, 모션 실행용으로 다시 ARM하세요.', true);
    return;
  }
  if (!controlSocketBound || !controlSocket || controlSocket.readyState !== WebSocket.OPEN) {
    showToast('제어 소켓 바인딩이 완료되지 않아 동작을 실행할 수 없습니다.', true);
    failSafeDisarm('action_socket_unavailable');
    return;
  }
  controlActionBusy = true;
  pendingControlActionId = id;
  actionConfirmation = null;
  renderControlActions();
  const sent = controlSocketSend({
    type: 'action', lease_id: controlLeaseId, seq: ++controlSequence,
    action_id: id, confirmed: Boolean(confirmed), client_time_ms: Date.now(),
  });
  if (!sent) {
    clearPendingControlAction();
    failSafeDisarm('action_send_failed', { notify: true });
    return;
  }
  controlActionAckTimer = setTimeout(() => {
    clearPendingControlAction();
    failSafeDisarm('action_ack_timeout', { notify: true });
  }, 1200);
}

function handleControlActionClick(event) {
  const button = event.target.closest('[data-control-action]');
  if (!button || button.disabled) return;
  const id = button.dataset.controlAction;
  if (button.dataset.confirm === 'true') {
    const now = Date.now();
    if (actionConfirmation?.id !== id || actionConfirmation.expires <= now) {
      actionConfirmation = { id, expires: now + 3500 };
      renderControlActions();
      setTimeout(() => {
        if (actionConfirmation?.id === id && actionConfirmation.expires <= Date.now()) {
          actionConfirmation = null;
          renderControlActions();
        }
      }, 3600);
      return;
    }
  }
  invokeControlAction(id, button.dataset.confirm === 'true');
}

function isFormControlTarget(target) {
  return Boolean(target?.closest?.('input, select, textarea, button, [contenteditable="true"]'));
}

function updateKeyboardGuide() {
  const keyMap = { KeyQ: 0, KeyW: 1, KeyE: 2, KeyA: 3, KeyS: 4, KeyD: 5 };
  const keys = Array.from(controlUi.keyboardGuide.querySelectorAll('.key-row kbd'));
  Object.entries(keyMap).forEach(([code, index]) => keys[index]?.classList.toggle('is-pressed', controlPressedKeys.has(code)));
  controlUi.keyboardGuide.querySelector('.shift-key kbd')?.classList.toggle('is-pressed', controlPressedKeys.has('ShiftLeft') || controlPressedKeys.has('ShiftRight'));
}

function handleControlKeyDown(event) {
  if (activePage !== 'controls' || controlLeaseSource !== 'keyboard' || !controlLeaseId || isFormControlTarget(event.target) || !controlInput.isControlCode(event.code)) return;
  event.preventDefault();
  if (event.repeat && controlPressedKeys.has(event.code)) return;
  controlPressedKeys.add(event.code);
  updateKeyboardGuide();
}

function handleControlKeyUp(event) {
  if (!controlInput.isControlCode(event.code) || !controlPressedKeys.has(event.code)) return;
  controlPressedKeys.delete(event.code);
  updateKeyboardGuide();
  if (controlLeaseId && controlLeaseSource === 'keyboard') {
    if (controlInput.deadmanReleaseEndsHold(controlPressedKeys, event.code)) {
      failSafeDisarm('keyboard_deadman_released', { notify: true });
    } else {
      // Direction release while Shift remains held is a normal stop, not a
      // lease release. Run immediately instead of waiting for the 50 ms tick.
      controlTick();
    }
  }
}

function releaseControlPointer(event) {
  const button = event.currentTarget;
  const wasDirection = controlPointerDirections.delete(event.pointerId);
  const wasDeadman = controlDeadmanPointers.delete(event.pointerId);
  button.classList.remove('is-pressed');
  if ((wasDirection || wasDeadman) && controlLeaseId) {
    const keyboardDeadman = controlInput.keyboardCommand(controlPressedKeys).deadman;
    if (wasDeadman && controlDeadmanPointers.size === 0 && !keyboardDeadman) {
      failSafeDisarm('pointer_deadman_released', { notify: true });
    } else {
      controlTick();
    }
  }
}

function bindControlPointerButtons() {
  controlUi.touchController.querySelectorAll('[data-control-direction], [data-control-deadman]').forEach((button) => {
    button.addEventListener('pointerdown', (event) => {
      if (!controlLeaseId || controlLeaseSource !== 'keyboard') return;
      event.preventDefault();
      try { button.setPointerCapture(event.pointerId); } catch (_) {}
      if (button.dataset.controlDirection) controlPointerDirections.set(event.pointerId, button.dataset.controlDirection);
      else controlDeadmanPointers.add(event.pointerId);
      button.classList.add('is-pressed');
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) => button.addEventListener(name, releaseControlPointer));
  });
}

function enterControlPage() {
  refreshControlGamepads();
  refreshControlSnapshot();
  controlBridgeServiceFeature?.refresh();
  if (controlLeaseId) connectControlSocket();
}

function leaveControlPage(reason = 'controls_page_left') {
  invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm(reason);
  else closeControlSocket(reason);
  resetControlInputs();
}

async function setRobotIp() {
  if (robotConnectionBusy) return;
  invalidateStateRequests();
  robotConnectionBusy = true;
  ui.connectButton.disabled = true;
  ui.connectButton.textContent = '확인 중…';
  try {
    const ip = ui.robotIp.value.trim();
    const candidate = selectedRobotCandidate?.ip === ip ? selectedRobotCandidate : null;
    const payload = window.RobotProfiles.connectionPayload(activeRobotProfile(), candidate, ip);
    const response = await api('/api/v1/robot', { method: 'POST', body: JSON.stringify(payload) });
    robotTargetConnected = response.robot?.connected !== false;
    if (response.robot?.changed) resetLiveRobotSessionView();
    robotRuntimeDataCompatible = !Boolean(response.robot?.restart_required)
      && (!response.robot_type || response.robot_type === selectedRobotType);
    robotTypeDirty = false;
    robotIpDirty = false;
    if (response.robot_type && response.robot_type !== selectedRobotType) activateRobotType(response.robot_type);
    const restartNote = response.robot?.restart_required
      ? ' DDS 재연결을 위해 해당 프로필로 대시보드를 다시 시작해야 하며, 그 전에는 Go2 제어가 차단됩니다.'
      : ' ROS 연결 설정은 별도로 확인하세요.';
    showToast(`${activeRobotProfile()?.label || '로봇'} 표시·확인 대상을 변경했습니다.${restartNote}`);
    await refreshState();
  } catch (error) {
    showToast(`IP 변경 실패: ${error.message}`, true);
    void refreshState();
  } finally {
    robotConnectionBusy = false;
    ui.connectButton.disabled = false;
    ui.disconnectButton.disabled = !robotTargetConnected;
    ui.connectButton.textContent = '연결';
  }
}

async function disconnectRobotTarget() {
  if (robotConnectionBusy || !robotTargetConnected) return;
  if (!window.confirm('현재 선택한 로봇 대상과 Go2 제어 권한을 해제할까요? 물리 네트워크와 로봇 전원은 변경되지 않습니다.')) return;
  invalidateStateRequests();
  robotConnectionBusy = true;
  ui.connectButton.disabled = true;
  ui.disconnectButton.disabled = true;
  ui.disconnectButton.textContent = '해제 중…';
  try {
    const response = await api('/api/v1/robot', { method: 'DELETE' });
    robotTargetConnected = false;
    robotRuntimeDataCompatible = false;
    robotIpDirty = false;
    selectedRobotCandidate = null;
    ui.robotIp.value = '';
    ui.connectedRobotTarget.textContent = '연결 안 됨';
    resetLiveRobotSessionView();
    latestState = null;
    renderOverviewUnavailable('로봇 대상 연결 해제됨', { clearLive: false });
    clearRobotDiscovery('연결 대상이 해제되었습니다. 검색하거나 IP를 입력해 다시 연결할 수 있습니다.');
    setDiscoveryStatus('연결 해제됨');
    const restartNote = response.robot?.restart_required
      ? ' Go2 DDS 제어를 다시 사용하려면 대상 연결 후 대시보드를 재시작하세요.'
      : '';
    showToast(`로봇 표시·제어 대상을 해제했습니다.${restartNote}`);
    await refreshState();
  } catch (error) {
    showToast(`연결 해제 실패: ${error.message}`, true);
    void refreshState();
  } finally {
    robotConnectionBusy = false;
    ui.connectButton.disabled = false;
    ui.disconnectButton.disabled = !robotTargetConnected;
    ui.disconnectButton.textContent = '연결 해제';
  }
}

function startClock() {
  const tick = () => { $('#clock').textContent = new Date().toLocaleTimeString('ko-KR', { hour12: false }); };
  tick(); setInterval(tick, 1000);
}

$('#connectButton').addEventListener('click', setRobotIp);
ui.disconnectButton.addEventListener('click', disconnectRobotTarget);
ui.robotType.addEventListener('change', () => activateRobotType(ui.robotType.value, { discover: true, dirty: true }));
ui.discoverRobotsButton.addEventListener('click', discoverRobots);
ui.robotIp.addEventListener('input', () => {
  robotIpDirty = true;
  if (selectedRobotCandidate?.ip === ui.robotIp.value.trim()) return;
  selectedRobotCandidate = null;
  ui.robotDiscoveryResults.querySelectorAll('.robot-candidate').forEach((button) => {
    button.classList.remove('is-selected');
    button.setAttribute('aria-pressed', 'false');
  });
});
ui.robotIp.addEventListener('keydown', (event) => { if (event.key === 'Enter') setRobotIp(); });
$('#refreshButton').addEventListener('click', async () => { await Promise.all([refreshState(), refreshTopics(), refreshSources(), refreshCameraCatalog(), datasetFeature?.refresh(), datasetFeature?.refreshSessions({ forceDetail: true }), refreshMappingControl(), refreshControlSnapshot(), controlBridgeServiceFeature?.refresh(true), refreshNavigation(), navigationLogFeature?.refresh(true), refreshNavigationParameters(true), serviceLifecycleFeature?.refresh(true)]); showToast('대시보드를 갱신했습니다.'); });
ui.mappingStartButton.addEventListener('click', startMappingSession);
ui.mappingSaveButton.addEventListener('click', saveMappingSession);
ui.mappingStopButton.addEventListener('click', stopMappingSession);
ui.cameraSource.addEventListener('change', () => {
  if (!cameraCatalog.length) {
    resetCameraRenderedFrame(ui.cameraSource.value, { reason: '카메라 소스를 변경하여 새 프레임을 기다리고 있습니다.' });
  }
  selectSource('camera', ui.cameraSource.value);
});
ui.cameraSingleMode.addEventListener('click', () => setCameraViewMode('single'));
ui.cameraDualMode.addEventListener('click', () => setCameraViewMode('dual'));
ui.cameraPrimarySource.addEventListener('change', () => selectPrimaryCamera(ui.cameraPrimarySource.value));
ui.cloudSource.addEventListener('change', () => {
  if (ui.cloudSource.value) chooseMapView('cloud');
  resetLiveCloudAccumulator();
  lastCloudSnapshot = null;
  pointcloudRequestGeneration += 1;
  cloudSeq = -1;
  renderLidarSourceIdentity('WAITING');
  selectSource('pointcloud', ui.cloudSource.value);
});
ui.odomSource.addEventListener('change', () => selectSource('odometry', ui.odomSource.value));
ui.mapSource.addEventListener('change', () => {
  if (ui.mapSource.value) chooseMapView('occupancy');
  mapSeq = -1;
  selectSource('occupancy_grid', ui.mapSource.value);
});
ui.mapViewMode.addEventListener('change', () => chooseMapView(ui.mapViewMode.value));
ui.livePointBudget.addEventListener('change', async () => {
  const value = ui.livePointBudget.value;
  ui.livePointCustomWrap.classList.toggle('is-hidden', value !== 'custom');
  if (value === 'custom') {
    ui.livePointCustom.focus();
    return;
  }
  if (value === 'all' && !window.confirm('ALL SESSION은 브라우저 세션 동안 최대 1,000,000점을 reservoir로 누적하므로 메모리와 렌더링 부하가 커질 수 있습니다. 계속할까요?')) {
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    return;
  }
  await applyLivePointLimit(value);
});
ui.livePointApply.addEventListener('click', () => applyLivePointLimit(ui.livePointCustom.value));
ui.livePointCustom.addEventListener('keydown', (event) => { if (event.key === 'Enter') applyLivePointLimit(ui.livePointCustom.value); });
ui.mapOverlayToggle.addEventListener('change', () => {
  mapOverlayVisible = ui.mapOverlayToggle.checked;
  redrawActiveMap();
});
ui.savedMapViewMode.addEventListener('change', () => chooseSavedMapView(ui.savedMapViewMode.value));
ui.savedPointBudget.addEventListener('change', async () => {
  const value = ui.savedPointBudget.value;
  ui.savedPointCustomWrap.classList.toggle('is-hidden', value !== 'custom');
  if (value === 'custom') {
    ui.savedPointCustom.focus();
    return;
  }
  await applySavedPointLimit(value);
});
ui.savedPointApply.addEventListener('click', () => applySavedPointLimit(ui.savedPointCustom.value));
ui.savedPointCustom.addEventListener('keydown', (event) => { if (event.key === 'Enter') applySavedPointLimit(ui.savedPointCustom.value); });
ui.savedMapOverlayToggle.addEventListener('change', () => {
  savedMapOverlayVisible = ui.savedMapOverlayToggle.checked;
  redrawSavedMap();
});
ui.savedMapList.addEventListener('click', (event) => {
  if (savedMapMutationBusy) return;
  const button = event.target.closest('[data-saved-map-id]');
  if (button) selectSavedMap(button.dataset.savedMapId);
});
ui.savedMapRenameButton.addEventListener('click', renameSelectedSavedMap);
ui.savedMapDeleteButton.addEventListener('click', deleteSelectedSavedMap);
ui.savedMapNameInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') renameSelectedSavedMap(); });
ui.mapConvertSource.addEventListener('change', () => {
  mapConversionNameDirty = false;
  mapConversionFeedback = null;
  syncMapConversionPanel();
});
ui.mapConvertName.addEventListener('input', () => {
  mapConversionNameDirty = true;
  mapConversionFeedback = null;
  syncMapConversionPanel();
});
[ui.mapConvertZMin, ui.mapConvertZMax, ui.mapConvertResolution, ui.mapConvertRadius, ui.mapConvertNeighbors].forEach((input) => {
  input.addEventListener('input', () => { mapConversionFeedback = null; syncMapConversionPanel(); });
});
ui.mapConvertBackground.addEventListener('change', () => {
  mapConversionFeedback = null;
  syncMapConversionPanel();
});
ui.mapConvertStart.addEventListener('click', startSavedMapConversion);
document.querySelectorAll('[data-map-editor-tool]').forEach((button) => {
  button.addEventListener('click', () => { mapEditorTool = button.dataset.mapEditorTool === 'eraser' ? 'eraser' : 'brush'; syncMapEditorUi(); });
});
document.querySelectorAll('[data-map-editor-value]').forEach((button) => {
  button.addEventListener('click', () => { mapEditorCellValue = Number(button.dataset.mapEditorValue); mapEditorTool = 'brush'; syncMapEditorUi(); });
});
ui.mapEditorBrushSize.addEventListener('input', syncMapEditorUi);
ui.mapEditorUndo.addEventListener('click', undoMapEditor);
ui.mapEditorRedo.addEventListener('click', redoMapEditor);
ui.mapEditorReset.addEventListener('click', resetMapEditor);
ui.mapEditorSaveName.addEventListener('input', syncMapEditorUi);
ui.mapEditorSaveName.addEventListener('keydown', (event) => { if (event.key === 'Enter') saveMapEditorCopy(); });
ui.mapEditorSave.addEventListener('click', saveMapEditorCopy);
ui.mapEditorCanvas.addEventListener('pointerdown', beginMapEditorStroke);
ui.mapEditorCanvas.addEventListener('pointermove', moveMapEditorStroke);
['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) => ui.mapEditorCanvas.addEventListener(name, finishMapEditorStroke));
mapAnnotationFeature = mapAnnotationEngine?.createFeature({
  ui: {
    state: ui.mapAnnotationState,
    type: ui.mapAnnotationType,
    name: ui.mapAnnotationName,
    draw: ui.mapAnnotationDraw,
    finish: ui.mapAnnotationFinish,
    cancel: ui.mapAnnotationCancel,
    list: ui.mapAnnotationList,
    message: ui.mapAnnotationMessage,
    discard: ui.mapAnnotationDiscard,
    save: ui.mapAnnotationSave,
    canvas: ui.navigationMapCanvas,
    hint: ui.navigationMapHint,
  },
  api,
  showToast,
  setStatePill,
  navigationEngine,
  context: () => ({
    mapSnapshot: navigationMapSnapshot,
    mapLayout: navigationMapLayout,
    mapCells: navigationMapCells,
    selectedMap: navigationSelectedMapMeta,
    mapLoadGeneration: navigationMapLoadGeneration,
    pipelineActive: navigationEngine?.pipelineActive(navigationSnapshot),
    operationBusy: navigationOperationBusy,
    goalAllowed: navigationPoseToolAllowed('goal'),
  }),
  drawPoseMarker: drawNavigationPoseMarker,
  drawMap: drawNavigationMap,
  renderNavigationStatus,
  renderPoseSelection: renderNavigationPoseSelection,
  discardNavigationPose,
  clearNavigationTool: () => { navigationMapTool = ''; },
  applyNavigationResponse: (response) => {
    const snapshot = extractNavigationSnapshot(response);
    if (snapshot) navigationSnapshot = snapshot;
  },
});
ui.navigationMapSelect.addEventListener('change', () => {
  const selected = navigationMapCandidates().find((entry) => entry.id === ui.navigationMapSelect.value);
  if (!selected) return;
  if (mapAnnotationFeature?.hasDirty() && !window.confirm('저장하지 않은 지도 주석 변경을 버리고 다른 지도를 열까요?')) {
    ui.navigationMapSelect.value = navigationSelectedMapMeta?.id || '';
    return;
  }
  loadNavigationMap(selected);
});
ui.navigationStartButton.addEventListener('click', startNavigation);
ui.navigationStopButton.addEventListener('click', stopNavigation);
ui.navigationInitialPoseTool.addEventListener('click', () => selectNavigationTool('initial'));
ui.navigationGoalPoseTool.addEventListener('click', () => selectNavigationTool('goal'));
ui.navigationPoseDiscard.addEventListener('click', () => discardNavigationPose());
ui.navigationPoseSend.addEventListener('click', sendNavigationPose);
ui.navigationCancelGoal.addEventListener('click', cancelNavigationGoal);
ui.navigationClearCostmaps.addEventListener('click', clearNavigationCostmaps);
ui.navigationMapCanvas.addEventListener('pointerdown', beginNavigationPose);
ui.navigationMapCanvas.addEventListener('pointermove', moveNavigationPose);
['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) => ui.navigationMapCanvas.addEventListener(name, finishNavigationPose));
ui.navigationParameterGroups.addEventListener('input', updateNavigationParameterDraft);
ui.navigationParameterGroups.addEventListener('change', updateNavigationParameterDraft);
ui.navigationPresetLoad.addEventListener('click', loadNavigationPreset);
ui.navigationParameterReset.addEventListener('click', resetNavigationParameterDraft);
ui.navigationParameterApply.addEventListener('click', applyNavigationParameters);
ui.topicSearch.addEventListener('input', renderTopics);
ui.categoryFilter.addEventListener('change', renderTopics);
ui.cameraCaptureButton.addEventListener('click', captureCameraFrame);
ui.cameraRecordButton.addEventListener('click', startCameraRecording);
ui.cameraStopRecordButton.addEventListener('click', () => stopCameraRecording());
controlUi.arm.addEventListener('click', armControl);
controlUi.disarm.addEventListener('click', () => failSafeDisarm('manual_disarm', { notify: true }));
controlUi.inputSource.addEventListener('change', () => {
  invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('input_source_changed', { notify: true });
  resetControlInputs();
  renderControlInputMode();
});
controlUi.gamepad.addEventListener('change', () => {
  invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('gamepad_selection_changed', { notify: true });
  selectedGamepadIndex = controlUi.gamepad.value;
  resetControlInputs();
  renderControlInputMode();
});
controlUi.speed.addEventListener('input', () => {
  controlUi.speedOutput.textContent = `${controlUi.speed.value}%`;
});
controlUi.estop.addEventListener('click', () => triggerEmergencyStop('dashboard_button'));
controlUi.clearConfirm.addEventListener('change', syncEstopClearButton);
controlUi.clear.addEventListener('click', clearEmergencyStop);
controlUi.actions.addEventListener('click', handleControlActionClick);
document.addEventListener('keydown', handleControlKeyDown);
document.addEventListener('keyup', handleControlKeyUp);
window.addEventListener('gamepadconnected', refreshControlGamepads);
window.addEventListener('gamepaddisconnected', refreshControlGamepads);
window.addEventListener('blur', () => {
  if (controlArmBusy) invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('window_blurred');
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    if (controlArmBusy) invalidatePendingArm();
    if (controlLeaseId) failSafeDisarm('document_hidden');
    if (cameraRecording) stopCameraRecording(cameraRecordingCleanupPolicy('visibility_hidden'));
  }
  syncPointcloudTransport();
  syncCameraTransport();
});
window.addEventListener('pagehide', () => {
  if (controlArmBusy) invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('page_hidden');
  disconnectPointcloud();
  disconnectCamera();
  discardCameraRecordingForPageHide();
});
window.addEventListener('pageshow', () => {
});
window.addEventListener('beforeunload', (event) => {
  if (!editorHasUnsavedChanges() && !mapAnnotationFeature?.hasDirty()) return;
  event.preventDefault();
  event.returnValue = '';
});
window.addEventListener('hashchange', () => activatePage(pageFromHash()));
window.addEventListener('resize', () => {
  if (activePage === 'mapping') redrawActiveMap();
  if (activePage === 'maps') { redrawSavedMap(); drawMapEditor(); }
  if (activePage === 'navigation') {
    navigationScene3d?.resize();
    drawNavigationMap();
  }
});

startClock();
initializeCameraMediaControls();
initializeCameraStreams();
datasetFeature = createDatasetFeature({ showToast });
datasetFeature.start();
window.RobotScopeDatasetCapture = datasetFeature;
window.RobotScopeDiagnosticsExport = createDiagnosticsExportFeature({ showToast }).start();
bindControlPointerButtons();
refreshControlGamepads();
renderControlStatus();
renderControlCommand();
syncMapConversionPanel();
syncMapEditorUi();
renderNavigationParameterGroups(navigationEngine?.TUNED_VALUES, true);
renderNavigationPresetOptions();
navigationLogFeature = initializeNavigationLogFeature({
  getActivePage: () => activePage,
  getNavigationSnapshot: () => navigationSnapshot,
  getNavigationApiAvailable: () => navigationApiAvailable,
});
renderNavigationStatus();
serviceLifecycleFeature = initializeServiceLifecycleFeature({
  showToast,
  getActivePage: () => activePage,
});
controlBridgeServiceFeature = initializeControlBridgeServiceFeature({
  showToast,
  getActivePage: () => activePage,
  refreshControl: refreshControlSnapshot,
  refreshNavigation,
});
activatePage(pageFromHash(), true);
ui.mappingSessionName.value = generatedMapName();
initializeRobotProfiles();
connectJoints();
connectPose();
requestAnimationFrame(animateRobot);
const pointBudgetReady = initializePointBudgets();
pointBudgetReady.then(() => loadOfflinePointcloud().then(refreshSavedMaps));
refreshState();
refreshTopics();
refreshSources();
pointBudgetReady.then(() => {
  syncPointcloudTransport();
  syncCameraTransport();
  refreshPointcloud();
});
refreshMap();
refreshMappingControl();
refreshNavigation();
navigationLogFeature.refresh();
refreshNavigationParameters();
serviceLifecycleFeature.refresh();
controlBridgeServiceFeature.refresh();
setInterval(refreshState, 1000);
setInterval(refreshPointcloud, 400);
setInterval(refreshMap, 2000);
setInterval(refreshTopics, 3500);
setInterval(refreshSources, 5000);
setInterval(refreshCameraCatalog, 5000);
setInterval(refreshSavedMaps, 15000);
setInterval(refreshMappingControl, 1000);
setInterval(refreshNavigation, 1000);
setInterval(markJointsStale, 250);
setInterval(syncCameraFrameFreshness, 500);
setInterval(controlTick, 50);
setInterval(refreshControlSnapshot, 1000);
setInterval(refreshControlGamepads, 1000);
