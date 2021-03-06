var tabs = {};
var currentTab = "logs";

var instance_state = null;
var updating = false;

function update() {
	if (updating)
		return;

	updating = true;
	wok.status.debug("Loading status ...");

	$.getJSON("/api/monitoring/instance/state/" + instance_name, function(data) {
		instance_state = data;
		if (tabs[currentTab] !== undefined)
			tabs[currentTab].update(data)
		wok.status.hide();
		updating = false;
	}).error(function(jqXHR, error_type, exception) {
		wok.status.error("Connection error loading status: " + error_type);
		updating = false;
	});
}

function tabChanged() {
	var selected = $("#tabs-buttons :checked").val();

	if (tabs[currentTab] !== undefined)
		tabs[currentTab].hide();

	if (tabs[selected] !== undefined) {
		if (instance_state !== null)
			tabs[selected].update(instance_state);
		tabs[selected].show();
	}

	currentTab = selected;
}

$(document).ready(function() {
	// tabs
	$("#tabs-body > div").addClass("tab").hide();
	$("#tab-btn-" + currentTab).attr("checked", "checked");

	tabs["modules"] = $("#tab-modules").modules({ instance_name: instance_name }).data("modules");
	tabs["logs"] = $("#tab-logs").logs({ instance_name: instance_name }).data("logs")

	$("#tabs-buttons").buttonset().change(tabChanged).trigger("change");

	update();
	
	window.setInterval(update, 10000);
});
