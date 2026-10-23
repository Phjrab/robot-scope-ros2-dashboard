// Existing saved-map scene setup and cloud counts shared by map views.
export function sameSavedCloudRevision(meta, selectedId, previousMeta, cloud) {
  // Retain the immutable reference during reload; changed selections still clear.
  return Boolean(meta.kind === 'pointcloud3d' && meta.revision &&
    selectedId === meta.id && previousMeta?.revision === meta.revision &&
    cloud?.revision === meta.revision && !cloud.demo_snapshot);
}

export function createSavedMapScene(ui, environment = window) {
  const savedScene3d = environment.RobotScene3D && ui.savedSceneCanvas
    ? new environment.RobotScene3D(ui.savedSceneCanvas, {
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

  return savedScene3d;
}

export function cloudPointCount(cloud) {
  return Number(cloud?.sent_points || (cloud?.points?.length ? Math.floor(cloud.points.length / 3) : 0));
}

export function cloudPointSummary(cloud) {
  const shown = cloudPointCount(cloud);
  const source = Math.max(shown, Number(cloud?.source_points || shown));
  return shown < source
    ? `${shown.toLocaleString()} / ${source.toLocaleString()}`
    : shown.toLocaleString();
}
