from xml.etree import ElementTree


def parse_xml(xml_text: str) -> ElementTree.Element:
    if "<!DOCTYPE" in xml_text.upper():
        raise ValueError("DOCTYPE declarations are not allowed in SMP XML")
    return ElementTree.fromstring(xml_text)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def text(element: ElementTree.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def first_child(element: ElementTree.Element | None, name: str) -> ElementTree.Element | None:
    if element is None:
        return None
    for child in element.iter():
        if local_name(child.tag) == name:
            return child
    return None


def element_to_dict(element: ElementTree.Element) -> dict[str, object]:
    children = list(element)
    payload: dict[str, object] = {
        "name": local_name(element.tag),
        "attributes": dict(element.attrib),
    }
    value = text(element)
    if value:
        payload["text"] = value
    if children:
        payload["children"] = [element_to_dict(child) for child in children]
    return payload
