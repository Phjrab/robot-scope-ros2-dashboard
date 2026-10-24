import { initializeLiveMapObservation } from './live_observation.js';
import { initializeGlobalMapObservation } from './global_observation.js';
import { initializeSensorTrackingObservation } from './sensor_tracking.js';

// Share lifecycle events only. Global jobs never receive a scene or a live
// model, and never request the continuous cloud/pose transport.
export function initializeSavedMapObservations(options) {
  const live = initializeLiveMapObservation(options);
  let sensor = null;
  const global = initializeGlobalMapObservation({ getContext: options.getContext,
    canChangeHistory: () => {
      const state = sensor?.snapshot();
      return Boolean(state && !state.active && !state.previewSuppressed && !state.stopRequested && !state.canRetry);
    } });
  sensor = initializeSensorTrackingObservation({ scene: options.scene,
    getContext: options.getContext, getGlobalRecord: () => global?.snapshot().record,
    onExclusive: active => live?.suspend(active) });
  return {
    wanted: () => live?.wanted() || false,
    render: changed => {
      global?.render();
      const sensorActive = sensor?.render() || false;
      const liveVisible = live?.render(changed) || false;
      if (sensorActive) sensor?.render();
      return sensorActive || liveVisible;
    },
    ingestPose: value => live?.ingestPose(value),
    ingestJoints: value => live?.ingestJoints(value),
    ingestCloud: value => { global?.ingestCloud(value); return live?.ingestCloud(value); },
    reset: reason => { global?.reset(reason); sensor?.reset(reason); live?.reset(reason); },
    destroy: () => { sensor?.destroy(); global?.destroy(); live?.destroy(); },
  };
}
