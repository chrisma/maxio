#!/usr/bin/env python3
#
# Script for converting reMarkable tablet ".rm" files to SVG image.
# this works for the new *.rm format, where each page is a seperate file
# credit for updating to version 5 rm files goes to
# https://github.com/peerdavid/rmapi/blob/master/tools/rM2svg
import sys
import struct
import os.path
import argparse


__prog_name__ = "rm2svg"
__version__ = "0.0.2"


# Size
default_x_width = 1404
default_y_width = 1872

# Mappings
stroke_colour = {
    0 : "black",
    1 : "grey",
    2 : "white",
}
'''stroke_width={
    0x3ff00000 : 2,
    0x40000000 : 4,
    0x40080000 : 8,
}'''


def main():
    parser = argparse.ArgumentParser(prog=__prog_name__)
    parser.add_argument('--height',
                        help='Desired height of image',
                        type=float,
                        default=default_y_width)
    parser.add_argument('--width',
                        help='Desired width of image',
                        type=float,
                        default=default_x_width)
    parser.add_argument("-i",
                        "--input",
                        help=".rm input file",
                        required=True,
                        metavar="FILENAME",
                        #type=argparse.FileType('r')
                        )
    parser.add_argument("-o",
                        "--output",
                        help="prefix for output files",
                        required=True,
                        metavar="NAME",
                        #type=argparse.FileType('w')
                        )
    parser.add_argument("-c",
                        "--coloured_annotations",
                        help="Colour annotations for document markup.",
                        action='store_true',
                        )
    parser.add_argument('--version',
                        action='version',
                        version='%(prog)s {version}'.format(version=__version__))
    args = parser.parse_args()

    if not os.path.exists(args.input):
        parser.error('The file "{}" does not exist!'.format(args.input))
    if args.coloured_annotations:
        set_coloured_annots()
    rm2svg(args.input, args.output, args.coloured_annotations,
           args.width, args.height)

def set_coloured_annots():
    global stroke_colour
    stroke_colour = {
        0: "black",
        1: "red",
        2: "white",
        3: "yellow"
    }

def abort(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def rm2svg(input_file, output_name, coloured_annotations=False,
              x_width=default_x_width, y_width=default_y_width):

    if coloured_annotations:
        set_coloured_annots()

    with open(input_file, 'rb') as f:
        data = f.read()
    offset = 0

    # Is this a reMarkable .lines file?
    expected_header_v3=b'reMarkable .lines file, version=3          '
    expected_header_v5=b'reMarkable .lines file, version=5          '
    if len(data) < len(expected_header_v5) + 4:
        abort('File too short to be a valid file')

    fmt = '<{}sI'.format(len(expected_header_v5))
    header, nlayers = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
    is_v3 = (header == expected_header_v3)
    is_v5 = (header == expected_header_v5)
    if (not is_v3 and not is_v5) or  nlayers < 1:
        abort('Not a valid reMarkable file: <header={}><nlayers={}>'.format(header, nlayers))
        return

    output = open(output_name, 'w')
    output.write('<svg xmlns="http://www.w3.org/2000/svg" height="{}" width="{}">'.format(y_width, x_width)) # BEGIN Notebook
    output.write('''
        <script type="application/ecmascript"> <![CDATA[
            var visiblePage = 'p1';
            function goToPage(page) {
                document.getElementById(visiblePage).setAttribute('style', 'display: none');
                document.getElementById(page).setAttribute('style', 'display: inline');
                visiblePage = page;
            }
        ]]> </script>
    ''')

    # Iterate through pages (There is at least one)
    output.write('<g id="p1" style="display:inline"><filter id="blurMe"><feGaussianBlur in="SourceGraphic" stdDeviation="10" /></filter>')

    for layer in range(nlayers):
        fmt = '<I'
        (nstrokes,) = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)

        # Iterate through the strokes in the layer (If there is any)
        for stroke in range(nstrokes):
            if is_v3:
                fmt = '<IIIfI'
                pen, colour, i_unk, width, nsegments = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
            if is_v5:
                fmt = '<IIIffI'
                pen, colour, i_unk, width, unknown, nsegments = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                #print('Stroke {}: pen={}, colour={}, width={}, unknown={}, nsegments={}'.format(stroke, pen, colour, width, unknown, nsegments))

            opacity = 1
            last_x = -1.; last_y = -1.
            last_width = 0

            # Brush and caligraphy
            if (pen == 0 or pen == 12  or pen == 21):   # Dynamic width, will be truncated into several strokes
                pass
            # Marker
            elif (pen == 3 or pen == 16):
                width = 64 * width - 112
                opacity = 0.9
            # BallPoint | Fineliner
            elif (pen == 2 or pen == 15) or (pen == 4 or pen == 17):
                width = 32 * width * width - 116 * width + 107
                if(x_width == default_x_width and y_width == default_y_width):
                    width *= 1.8
            # Pencil and mech
            elif (pen == 7 or pen == 13) or (pen == 1 or pen == 14):
                width = 16 * width - 27
                opacity = 0.9
            # Highlighter
            elif (pen == 5 or pen == 18):
                width = 30
                opacity = 0.2
                if coloured_annotations:
                    colour = 3
            elif (pen == 8): # Erase area
                opacity = 0.
            elif (pen == 6): # Eraser
                width = 1280 * width * width - 4800 * width + 4510
                colour = 2
            else:
                print('Unknown pen: {}'.format(pen))
                opacity = 0.

            width /= 2.3 # adjust for transformation to A4

            #print('Stroke {}: pen={}, colour={}, width={}, nsegments={}'.format(stroke, pen, colour, width, nsegments))
            output.write('<polyline style="fill:none;stroke:{};stroke-width:{};opacity:{}" points="'.format(stroke_colour[colour], width, opacity)) # BEGIN stroke

            # Iterate through the segments to form a polyline
            for segment in range(nsegments):
                fmt = '<ffffff'
                xpos, ypos, speed, tilt, width, pressure = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                #xpos += 60
                #ypos -= 20
                ratio = (y_width/x_width)/(1872/1404)
                if ratio > 1:
                    xpos = ratio*((xpos*x_width)/1404)
                    ypos = (ypos*y_width)/1872
                else:
                    xpos = (xpos*x_width)/1404
                    ypos = (1/ratio)*(ypos*y_width)/1872

                if (pen == 21): #  caligraphhy
                    if 0 == segment % 2:
                        segment_width = 0.9 * (((1+pressure) * (1 * width)) - 0.3*tilt) + (0.1 * last_width)
                        output.write('"/>\n<polyline style="fill:none; stroke:black; stroke-width:{}" stroke-linecap="round" points="'.format(segment_width))
                        if last_x != -1.:
                            output.write('{:.3f},{:.3f} '.format(last_x, last_y)) # Join to previous segment
                        last_x = xpos; last_y = ypos; last_width = segment_width
                elif (pen == 12): # brush
                    if 0 == segment % 3:
                        segment_width = 1 * (((1+(1.4*pressure)) * (1 * width)) - (0.5*tilt) - (0.5*speed/50)) #+ (0.2 * last_width)
                        segment_opacity = pressure * pressure - 0.2 * (speed / 50)
                        # opacity must be between 1 and 0
                        segment_opacity = 1 if segment_opacity > 1 else segment_opacity
                        segment_opacity = 0 if segment_opacity < 0 else segment_opacity
                        # using segment color not opacity because the dots interfere with each other.
                        # Color must be 255 rgb
                        segment_color = [int(abs(segment_opacity-1)*255)]*3
                        segment_opacity = 1
#                        output.write('"/>\n<polyline style="fill:none;stroke:rgb({});stroke-width:{:.3f};opacity:{:.3f}" stroke-linecap="round" points="'.format(
#                                    str(tuple(segment_color)), segment_width, segment_opacity)) # UPDATE stroke
                        output.write('"/>\n<polyline style="fill:none; stroke:rgb{} ;stroke-width:{:.3f}" stroke-linecap="round" points="'.format(
                                    str(tuple(segment_color)), segment_width)) # UPDATE stroke

                        if last_x != -1.:
                            output.write('{:.3f},{:.3f} '.format(last_x, last_y)) # Join to previous segment
                    last_x = xpos; last_y = ypos; last_width = segment_width

                output.write('{:.3f},{:.3f} '.format(xpos, ypos)) # BEGIN and END polyline segment

            output.write('" />\n') # END stroke

    # Overlay the page with a clickable rect to flip pages
    output.write('<rect x="0" y="0" width="{}" height="{}" fill-opacity="0"/>'.format(x_width, y_width))
    output.write('</g>') # Closing page group
    output.write('</svg>') # END notebook
    output.close()

def extract_data(input_file):
    """
    gets stroke information as a list. Useful for figuring out which value does what.
    """

    with open(input_file, 'rb') as f:
        data = f.read()
    offset = 0

    # Is this a reMarkable .lines file?
    expected_header_v3=b'reMarkable .lines file, version=3          '
    expected_header_v5=b'reMarkable .lines file, version=5          '
    if len(data) < len(expected_header_v5) + 4:
        abort('File too short to be a valid file')

    fmt = '<{}sI'.format(len(expected_header_v5))
    header, nlayers = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
    is_v3 = (header == expected_header_v3)
    is_v5 = (header == expected_header_v5)
    if (not is_v3 and not is_v5) or  nlayers < 1:
        abort('Not a valid reMarkable file: <header={}><nlayers={}>'.format(header, nlayers))
        return

    my_list = []
    for layer in range(nlayers):
        fmt = '<I'
        (nstrokes,) = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)

        # Iterate through the strokes in the layer (If there is any)
        for stroke in range(nstrokes):
            if is_v5:
                fmt = '<IIIffI'
                pen, colour, i_unk, width, i_unk4, nsegments = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                #print('Stroke {}: pen={}, colour={}, width={}, unknown={}, nsegments={}'.format(stroke, pen, colour, width, unknown, nsegments))

            # Iterate through the segments to form a polyline
            for segment in range(nsegments):
                fmt = '<ffffff'
                xpos, ypos, pressure, tilt, i_unk2, i_unk3 = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                #xpos += 60
                #ypos -= 20
                my_list.append([pen, colour, i_unk, width, i_unk4, nsegments, xpos, ypos, pressure, tilt, i_unk2, i_unk3])
    return my_list


if __name__ == "__main__":
    main()