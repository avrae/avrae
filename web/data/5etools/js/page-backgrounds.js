function parsesize (size) {
	if (size == "T") size = "Tiny";
	if (size == "S") size = "Small";
	if (size == "M") size = "Medium";
	if (size == "L") size = "Large";
	if (size == "H") size = "Huge";
	if (size == "G") size = "Gargantuan";
	return size;
}

function tagcontent (curitem, tag, multi=false) {
	if (!curitem.getElementsByTagName(tag).length) return false;
	return curitem.getElementsByTagName(tag)[0].childNodes[0].nodeValue;
}

window.onload = loadbackgrounds;

var tabledefault = "";

function loadbackgrounds () {
	tabledefault = $("#stats").html();
	var bglist = backgrounddata.compendium.background;

	for (var i = 0; i < bglist.length; i++) {
		var curbg = bglist[i];
		var name = curbg.name;
		$("ul.backgrounds").append("<li id='"+i+"' data-link='"+encodeURI(name)+"'><span class='name'>"+name.replace("Variant ","")+"</span></li>");
	}

	var options = {
		valueNames: ['name'],
		listClass: "backgrounds"
	}

	var backgroundslist = new List("listcontainer", options);
	backgroundslist.sort ("name")

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
		usebackground($(this).attr("id"));
		document.title = decodeURI($(this).attr("data-link")) + " - 5etools Backgrounds";
		window.location = "#"+$(this).attr("data-link");
	});

	if (window.location.hash.length) {
		$("ul.list li[data-link='"+window.location.hash.split("#")[1]+"']:eq(0)").click();
	} else $("ul.list li:eq(0)").click();
}

function usebackground (id) {
	$("#stats").html(tabledefault);
	var bglist = backgrounddata.compendium.background;
	var curbg = bglist[id];

	var name = curbg.name;
	$("th#name").html(name);

	var traitlist = curbg.trait;
	$("tr.trait").remove();
	for (var n = traitlist.length-1; n >= 0; n--) {
		var traitname = traitlist[n].name;
		var texthtml = "<span class='name'>"+traitname+".</span> ";
		var textlist = traitlist[n].text;
		texthtml = texthtml + "<span>"+textlist[0]+"</span> "

		for (var i = 1; i < textlist.length; i++) {
			if (!textlist[i]) continue;
			if (textlist[i].indexOf ("Source: ") !== -1) continue;
			texthtml = texthtml + "<p>"+textlist[i]+"</p>";
		}

		$("tr#traits").after("<tr class='trait'><td colspan='6' class='trait"+i+"'>"+texthtml+"</td></tr>");
	}

};
