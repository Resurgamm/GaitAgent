package ai.pediamed.childgait.ui.screens

import ai.pediamed.childgait.data.model.AnalysisStage
import ai.pediamed.childgait.data.model.CameraSlot
import ai.pediamed.childgait.data.model.SessionInput
import ai.pediamed.childgait.ui.AnalysisUiState
import ai.pediamed.childgait.util.formatDurationSeconds
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

@Composable
fun AnalysisScreen(
    input: SessionInput,
    analysis: AnalysisUiState,
    modifier: Modifier = Modifier,
) {
    val stages = AnalysisStage.entries
    val currentIndex = stages.indexOf(analysis.stage)

    val overall = ((currentIndex + analysis.fraction) / stages.size).coerceIn(0f, 1f)
    val animated by animateFloatAsState(targetValue = overall, label = "overall")

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(20.dp),
    ) {
        Text(
            text = "Analysing two clips",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onBackground,
        )

        Spacer(Modifier.height(16.dp))

        input.clips.forEach { clip ->
            val accent = when (clip.slot) {
                CameraSlot.SAGITTAL -> SagittalAccent
                CameraSlot.CORONAL -> CoronalAccent
            }
            val active = analysis.currentSlot == clip.slot

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 5.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    modifier = Modifier
                        .size(width = 4.dp, height = 34.dp)
                        .background(accent, RoundedCornerShape(2.dp))
                )
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = clip.video.displayName,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = "${clip.slot.label} · " +
                            "${formatDurationSeconds(clip.video.durationMs)} · " +
                            clip.slot.shortHint,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (active) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                    )
                }
            }
        }

        Spacer(Modifier.height(24.dp))

        LinearProgressIndicator(
            progress = { animated },
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp),
        )

        Spacer(Modifier.height(24.dp))

        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            stages.forEachIndexed { index, stage ->
                val suffix = if (index == currentIndex && analysis.currentSlot != null) {
                    " — ${analysis.currentSlot.label.lowercase()}"
                } else {
                    ""
                }
                StageRow(
                    label = stage.label + suffix,
                    isDone = index < currentIndex,
                    isActive = index == currentIndex,
                )
            }
        }
    }
}

@Composable
private fun StageRow(label: String, isDone: Boolean, isActive: Boolean) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        when {
            isDone -> Icon(
                imageVector = Icons.Filled.CheckCircle,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(20.dp),
            )

            isActive -> CircularProgressIndicator(
                modifier = Modifier.size(20.dp),
                strokeWidth = 2.dp,
            )

            else -> Icon(
                imageVector = Icons.Filled.RadioButtonUnchecked,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.outline,
                modifier = Modifier.size(20.dp),
            )
        }

        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = if (isDone || isActive) {
                MaterialTheme.colorScheme.onSurface
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            },
        )
    }
}
