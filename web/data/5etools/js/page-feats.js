

function parsesize (size) {
	if (size == "T") size = "Tiny";
	if (size == "S") size = "Small";
	if (size == "M") size = "Medium";
	if (size == "L") size = "Large";
	if (size == "H") size = "Huge";
	if (size == "G") size = "Gargantuan";
	return size;
}

window.onload = loadfeats;
var tabledefault = "";

function loadfeats() {
	tabledefault = $("#stats").html();
	var featlist = featdata.compendium.feat;

		for (var i = 0; i < featlist.length; i++) {
			var curfeat = featlist[i];
			var name = curfeat.name;
			$("ul.feats").append("<li id='"+i+"' data-link='"+encodeURI(name)+"'><span class='name'>"+name+"</span></li>");
		}

		var options = {
			valueNames: ['name'],
			listClass: "feats"
		}

		var featslist = new List("listcontainer", options);
		featslist.sort ("name")

		$("ul.list li").mousedown(function(e) {
			if (e.which === 2) {
				console.log("#"+$(this).attr("data-link"))
				window.open("#"+$(this).attr("data-link"), "_blank").focus();
				e.preventDefault();
				e.stopPropagation();
				return;
			}
		});

		$("ul.list li").click(function(e) {
			usefeat($(this).attr("id"));
			document.title = decodeURI($(this).attr("data-link")) + " - 5etools Feats";
			window.location = "#"+$(this).attr("data-link");
		});

		if (window.location.hash.length) {
			$("ul.list li[data-link='"+window.location.hash.split("#")[1]+"']:eq(0)").click();
		} else $("ul.list li:eq(0)").click();
	}

	function usefeat (id) {
			$("#stats").html(tabledefault);
			var featlist = featdata.compendium.feat;
			var curfeat = featlist[id];

			var name = curfeat.name;
			$("th#name").html(name);

			$("td#prerequisite").html("")
			var prerequisite = curfeat.prerequisite;
			if (prerequisite) $("td#prerequisite").html("Prerequisite: "+prerequisite);

			$("tr.text").remove();

			var textlist = curfeat.text;
			var texthtml = "";

			for (var i = 0; i < textlist.length; i++) {
				if (!textlist[i]) continue;
				texthtml = texthtml + "<p>"+textlist[i]+"</p>";
			}

			$("tr#text").after("<tr class='text'><td colspan='6' class='text"+i+"'>"+texthtml+"</td></tr>");

		};
