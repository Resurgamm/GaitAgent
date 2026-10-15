package ai.pediamed.childgait.ui

import ai.pediamed.childgait.data.model.AnalysisProgress
import ai.pediamed.childgait.data.model.AnalysisStage
import ai.pediamed.childgait.data.model.CameraSlot
import ai.pediamed.childgait.data.model.Clip
import ai.pediamed.childgait.data.model.SessionInput
import ai.pediamed.childgait.data.model.SessionReport
import ai.pediamed.childgait.data.model.VideoSource
import ai.pediamed.childgait.di.AppModule
import ai.pediamed.childgait.pose.PoseTrack
import ai.pediamed.childgait.util.VideoMetadata
import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AnalysisUiState(
    val stage: AnalysisStage = AnalysisStage.READING,
    val fraction: Float = 0f,
    val currentSlot: CameraSlot? = null,
    val scoresReceived: Int = 0,
    val scoresTotal: Int = 34,
)

data class SessionUiState(
    /** Clips picked so far, keyed by camera slot. */
    val picked: Map<CameraSlot, VideoSource> = emptyMap(),
    val isAnalyzing: Boolean = false,
    val analyzingInput: SessionInput? = null,
    val analysis: AnalysisUiState = AnalysisUiState(),
    val report: SessionReport? = null,
    val error: String? = null,
    val selectedSlot: CameraSlot? = null,
    val poseTrack: PoseTrack = PoseTrack.EMPTY,
    val isTrackingPose: Boolean = false,
) {
    val sagittal: VideoSource? get() = picked[CameraSlot.SAGITTAL]
    val coronal: VideoSource? get() = picked[CameraSlot.CORONAL]

    val isReadyToAnalyze: Boolean
        get() = sagittal != null && coronal != null

    val selectedClip: Clip?
        get() = selectedSlot?.let { slot -> report?.input?.clip(slot) }
}

class SessionViewModel(application: Application) : AndroidViewModel(application) {

    private val analyzer = AppModule.gaitAnalyzer(application)
    private val poseTracker = AppModule.poseTracker(application)

    private val _state = MutableStateFlow(SessionUiState())
    val state: StateFlow<SessionUiState> = _state.asStateFlow()

    val engineName: String get() = analyzer.engineName
    val isMockEngine: Boolean get() = analyzer.isMock

    private var analysisJob: Job? = null
    private var poseJob: Job? = null

    fun onClipPicked(slot: CameraSlot, uri: Uri) {
        viewModelScope.launch {
            val video = VideoMetadata.read(getApplication(), uri)
            if (video.durationMs <= 0L) {
                _state.update { it.copy(error = "That file could not be read as a video.") }
                return@launch
            }
            _state.update { it.copy(picked = it.picked + (slot to video)) }
        }
    }

    fun onClipCleared(slot: CameraSlot) {
        _state.update { it.copy(picked = it.picked - slot) }
    }

    fun analyze() {
        val current = _state.value
        val sagittal = current.sagittal ?: return
        val coronal = current.coronal ?: return
        val input = SessionInput(
            sagittal = sagittal,
            coronal = coronal,
        )

        analysisJob?.cancel()
        poseJob?.cancel()
        _state.update {
            it.copy(
                isAnalyzing = true,
                analyzingInput = input,
                report = null,
                analysis = AnalysisUiState(),
                error = null,
            )
        }

        analysisJob = viewModelScope.launch {
            analyzer.analyze(input).collect { progress ->
                when (progress) {
                    is AnalysisProgress.Stage -> _state.update {
                        it.copy(
                            analysis = it.analysis.copy(
                                stage = progress.stage,
                                fraction = progress.fraction,
                                currentSlot = progress.currentSlot,
                            ),
                        )
                    }

                    is AnalysisProgress.ScoreUpdate -> _state.update {
                        it.copy(
                            report = progress.report,
                            isAnalyzing = true,
                            analysis = it.analysis.copy(
                                stage = AnalysisStage.SCORING,
                                fraction = (progress.received.toFloat() /
                                    progress.total.coerceAtLeast(1))
                                    .coerceIn(0.1f, 0.99f),
                                scoresReceived = progress.received,
                                scoresTotal = progress.total,
                            ),
                        )
                    }

                    is AnalysisProgress.Complete -> _state.update {
                        it.copy(
                            isAnalyzing = false,
                            report = progress.report,
                            analysis = it.analysis.copy(
                                fraction = 1f,
                                scoresReceived = progress.report.aggregated.size,
                                scoresTotal = 34,
                            ),
                        )
                    }

                    is AnalysisProgress.Failed -> _state.update {
                        it.copy(isAnalyzing = false, error = progress.message)
                    }
                }
            }
        }
    }

    fun onClipSelected(slot: CameraSlot) {
        val clip = _state.value.report?.input?.clip(slot) ?: return

        poseJob?.cancel()
        _state.update {
            it.copy(selectedSlot = slot, poseTrack = PoseTrack.EMPTY, isTrackingPose = true)
        }

        poseJob = viewModelScope.launch {
            val track = poseTracker.track(clip)
            _state.update {
                if (it.selectedSlot == slot) {
                    it.copy(poseTrack = track, isTrackingPose = false)
                } else {
                    it
                }
            }
        }
    }

    fun clearSelectedClip() {
        poseJob?.cancel()
        _state.update {
            it.copy(selectedSlot = null, poseTrack = PoseTrack.EMPTY, isTrackingPose = false)
        }
    }

    fun reset() {
        analysisJob?.cancel()
        poseJob?.cancel()
        _state.value = SessionUiState()
    }

    fun dismissError() {
        _state.update { it.copy(error = null) }
    }

    override fun onCleared() {
        super.onCleared()
        poseTracker.close()
    }
}
