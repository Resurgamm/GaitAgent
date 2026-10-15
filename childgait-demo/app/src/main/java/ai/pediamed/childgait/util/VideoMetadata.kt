package ai.pediamed.childgait.util

import ai.pediamed.childgait.data.model.VideoSource
import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Reads the identity of a picked video: display name, duration, size.
 *
 * These three fields are also what the mock analyzer seeds from, so a given file always produces
 * the same report.
 */
object VideoMetadata {

    suspend fun read(context: Context, uri: Uri): VideoSource = withContext(Dispatchers.IO) {
        var displayName = "Session recording"
        var sizeBytes = 0L

        runCatching {
            context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                        .takeIf { it >= 0 }
                        ?.let { if (!cursor.isNull(it)) displayName = cursor.getString(it) }
                    cursor.getColumnIndex(OpenableColumns.SIZE)
                        .takeIf { it >= 0 }
                        ?.let { if (!cursor.isNull(it)) sizeBytes = cursor.getLong(it) }
                }
            }
        }

        val durationMs = runCatching {
            val retriever = MediaMetadataRetriever()
            try {
                retriever.setDataSource(context, uri)
                retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                    ?.toLongOrNull() ?: 0L
            } finally {
                runCatching { retriever.release() }
            }
        }.getOrDefault(0L)

        VideoSource(
            uri = uri.toString(),
            displayName = displayName,
            durationMs = durationMs,
            sizeBytes = sizeBytes,
        )
    }
}

/** `1:04:12` for long recordings, `4:32` otherwise. */
fun formatTimestamp(millis: Long): String {
    val totalSeconds = (millis / 1000).coerceAtLeast(0)
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    return if (hours > 0) {
        "%d:%02d:%02d".format(hours, minutes, seconds)
    } else {
        "%d:%02d".format(minutes, seconds)
    }
}

fun formatDurationSeconds(millis: Long): String = "%.1fs".format(millis / 1000f)
