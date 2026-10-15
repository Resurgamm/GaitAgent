package ai.pediamed.childgait.util

import ai.pediamed.childgait.data.model.SessionReport
import android.content.Context
import android.content.Intent
import org.json.JSONArray
import org.json.JSONObject

/**
 * Serialises a report to JSON and hands it to the share sheet.
 *
 * The `disclaimer` and `engine` fields are written first and are not optional: an exported file
 * outlives the screen it came from, and it must carry its own warning that the scores are mocked.
 */
object ReportExport {

    fun toJson(report: SessionReport, engineName: String): String {
        val root = JSONObject()
        root.put(
            "disclaimer",
            "DEMO OUTPUT — synthetic scores from a mock engine. Not for clinical use.",
        )
        root.put("engine", engineName)
        root.put("schemaVersion", 2)

        root.put(
            "clips",
            JSONArray().apply {
                report.input.clips.forEach { clip ->
                    put(
                        JSONObject().apply {
                            put("slot", clip.slot.code)
                            put("view", clip.view.name)
                            put("displayName", clip.video.displayName)
                            put("durationMs", clip.video.durationMs)
                            put("sizeBytes", clip.video.sizeBytes)
                            put("quality", report.qualityOf(clip.slot).toDouble())
                            put("resolvesScores", report.scoresFrom(clip.slot).size)
                        }
                    )
                }
            }
        )

        root.put(
            "summary",
            JSONObject().apply {
                put("overall", report.overall.name)
                put("flaggedItems", report.flaggedCount)
                put("totalItems", report.totalItems)
                put("meanConfidence", report.meanConfidence.toDouble())
                put("patternSummary", report.patternSummary)
            }
        )

        root.put(
            "scores",
            JSONArray().apply {
                report.aggregated.forEach { score ->
                    put(
                        JSONObject().apply {
                            put("item", score.item.code)
                            put("itemName", score.item.displayName)
                            put("limb", score.limb.code)
                            // Which clip resolved this item, so a reader can trace every score
                            // back to the camera that could actually see it.
                            put("view", score.item.view.name)
                            put("label", score.label.name)
                            put("confidence", score.confidence.toDouble())
                        }
                    )
                }
            }
        )

        return root.toString(2)
    }

    fun share(context: Context, report: SessionReport, engineName: String) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, "ChildGait demo report (mock)")
            putExtra(Intent.EXTRA_TEXT, toJson(report, engineName))
        }
        context.startActivity(Intent.createChooser(intent, "Export report"))
    }
}
