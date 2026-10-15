package ai.pediamed.childgait

import ai.pediamed.childgait.ui.SessionViewModel
import ai.pediamed.childgait.ui.components.DemoBanner
import ai.pediamed.childgait.ui.screens.AnalysisScreen
import ai.pediamed.childgait.ui.screens.ClipDetailScreen
import ai.pediamed.childgait.ui.screens.ImportScreen
import ai.pediamed.childgait.ui.screens.ReportScreen
import ai.pediamed.childgait.ui.theme.ChildGaitTheme
import ai.pediamed.childgait.util.ReportExport
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ChildGaitTheme {
                ChildGaitApp()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChildGaitApp(viewModel: SessionViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }

    state.error?.let { message ->
        LaunchedEffect(message) {
            snackbarHostState.showSnackbar(message)
            viewModel.dismissError()
        }
    }

    // Back navigates the stack we actually have: clip detail -> report -> import.
    BackHandler(enabled = state.selectedSlot != null) {
        viewModel.clearSelectedClip()
    }
    BackHandler(enabled = state.selectedSlot == null && state.report != null && !state.isAnalyzing) {
        viewModel.reset()
    }

    val title = when {
        state.selectedClip != null -> "${state.selectedClip?.slot?.label} clip"
        state.report != null && state.isAnalyzing ->
            "Scoring ${state.analysis.scoresReceived}/${state.analysis.scoresTotal}"
        state.report != null -> "Session report"
        state.isAnalyzing -> "Analysing"
        else -> "ChildGait"
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    if (state.selectedSlot != null || (state.report != null && !state.isAnalyzing)) {
                        IconButton(
                            onClick = {
                                if (state.selectedSlot != null) {
                                    viewModel.clearSelectedClip()
                                } else {
                                    viewModel.reset()
                                }
                            }
                        ) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = "Back",
                            )
                        }
                    }
                },
            )
        },
    ) { innerPadding ->
        Column(modifier = Modifier.fillMaxSize().padding(innerPadding)) {
            if (viewModel.isMockEngine) {
                DemoBanner(engineName = viewModel.engineName)
            }

            val report = state.report
            val selectedClip = state.selectedClip
            val analyzingInput = state.analyzingInput

            when {
                report != null && selectedClip != null -> ClipDetailScreen(
                    clip = selectedClip,
                    scores = report.scoresFrom(selectedClip.slot),
                    quality = report.qualityOf(selectedClip.slot),
                    poseTrack = state.poseTrack,
                    isTrackingPose = state.isTrackingPose,
                )

                report != null -> ReportScreen(
                    report = report,
                    onClipClick = viewModel::onClipSelected,
                    onShare = { ReportExport.share(context, report, viewModel.engineName) },
                    onNewSession = viewModel::reset,
                    isAnalyzing = state.isAnalyzing,
                    scoresReceived = state.analysis.scoresReceived,
                    scoresTotal = state.analysis.scoresTotal,
                )

                analyzingInput != null && state.isAnalyzing -> AnalysisScreen(
                    input = analyzingInput,
                    analysis = state.analysis,
                )

                else -> ImportScreen(
                    sagittal = state.sagittal,
                    coronal = state.coronal,
                    isReadyToAnalyze = state.isReadyToAnalyze,
                    onClipPicked = viewModel::onClipPicked,
                    onClipCleared = viewModel::onClipCleared,
                    onAnalyze = viewModel::analyze,
                )
            }
        }
    }
}
